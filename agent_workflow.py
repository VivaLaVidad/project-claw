"""
Project Claw v11.0 - Agent Workflow
防幻觉商业交易状态机

架构：
  router_node
    ├── inquiry / bargain  ->  rag_inventory_node  ->  negotiator_node
    └── chat               ->  negotiator_node

工程标准：
  - 全异步 async/await
  - tenacity 自动重试（3次，指数退避）
  - TypedDict State 类型安全
  - 枚举保证意图合法性
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from enum import Enum
from typing import Optional
from typing_extensions import TypedDict
from uuid import uuid4

import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
try:
    from langgraph.graph import StateGraph, END
    _LANGGRAPH_AVAILABLE = True
except ImportError:
    _LANGGRAPH_AVAILABLE = False
    StateGraph = None
    END = "__end__"

from config import settings
from llm_client import LLMClient
from local_memory import get_store
from shared.claw_protocol import A2A_MerchantOffer, A2A_TradeIntent

logger = logging.getLogger(__name__)


# ==================== 枚举 ====================

class IntentType(str, Enum):
    INQUIRY = "inquiry"
    BARGAIN = "bargain"
    CHAT    = "chat"
    DEAL    = "deal"    # 用户明确接受价格，准备付款


# ==================== State ====================

class AgentState(TypedDict):
    session_id:       str
    latest_msg:       str
    intent_type:      Optional[str]
    inventory_status: Optional[dict]
    draft_reply:      Optional[str]
    final_reply:      Optional[str]
    deal_price:       Optional[float]   # 成交价格，由 PaymentNode 使用
    payment_triggered: Optional[bool]   # 是否已触发收款


# ==================== LLM 异步调用（Retry）====================

# ── LLM 客户端（统一接入，消除硬编码）──────────────────────
def _get_llm_client(max_tokens: int = 200, temperature: float = 0.3) -> "LLMClient":
    """从 settings 获取配置，懒创建 LLMClient。"""
    return LLMClient(
        api_key     = settings.DEEPSEEK_API_KEY,
        api_url     = settings.DEEPSEEK_API_URL,
        model       = settings.DEEPSEEK_MODEL,
        temperature = temperature,
        max_tokens  = max_tokens,
        timeout     = settings.DEEPSEEK_TIMEOUT,
        max_retries = settings.DEEPSEEK_MAX_RETRIES,
    )


async def _call_llm_async(
    messages: list,
    max_tokens: int = 200,
    temperature: float = 0.3,
) -> str:
    """
    异步调用 LLM（通过 LLMClient 统一封装）。
    tenacity 重试已在 LLMClient._call() 内部处理。
    asyncio.to_thread 保证不阻塞事件循环。
    """
    client = _get_llm_client(max_tokens=max_tokens, temperature=temperature)
    result = await asyncio.to_thread(client.ask_messages, messages, temperature)
    if result is None:
        raise RuntimeError("LLMClient 返回 None，可能 API Key 无效或服务不可用")
    return result


def _parse_json(raw: str) -> dict:
    """从 LLM 输出中安全提取 JSON"""
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0].strip()
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0].strip()
    return json.loads(raw)


# ==================== 本地库存数据库（模拟）====================

_INVENTORY: dict = {
    "牛肉面": {"floor": 12.0, "price": 18.0, "stock": 15},
    "麻辣烫": {"floor":  9.0, "price": 15.0, "stock": 20},
    "水饺":   {"floor":  5.0, "price":  8.0, "stock":  8},
    "炒饭":   {"floor":  8.0, "price": 12.0, "stock": 12},
    "凉皮":   {"floor":  6.0, "price": 10.0, "stock": 10},
    "套餐A":  {"floor": 18.0, "price": 25.0, "stock":  5},
}


def _query_inventory(msg: str) -> dict:
    """关键词匹配库存，可替换为 ChromaDB 语义检索"""
    for name, data in _INVENTORY.items():
        if name in msg:
            return {
                "found": True,
                "item": name,
                "floor_price": data["floor"],
                "normal_price": data["price"],
                "stock": data["stock"],
                "low_stock": data["stock"] < 5,
            }
    return {
        "found": False, "item": None,
        "floor_price": None, "normal_price": None,
        "stock": None, "low_stock": False,
    }


# ==================== Node 函数 ====================

async def router_node(state: AgentState) -> AgentState:
    """意图路由节点，严格输出 JSON: {"intent": "..."}  """
    msg = state["latest_msg"]
    logger.info(f"[RouterNode] {msg[:40]}")

    system = (
        "你是餐厅智能路由助手。\n"
        "严格按 JSON 格式输出意图，不要任何解释。\n"
        "可选：inquiry（询价）, bargain（砍价）, chat（闲聊）\n"
        'JSON格式: {"intent": "inquiry"}'
    )
    try:
        raw = await _call_llm_async(
            [{"role": "system", "content": system},
             {"role": "user",   "content": msg}],
            max_tokens=20,
            temperature=0.0,
        )
        intent_str = _parse_json(raw).get("intent", "chat").lower()
        intent = (
            IntentType(intent_str)
            if intent_str in IntentType._value2member_map_
            else IntentType.CHAT
        )
    except Exception as e:
        logger.warning(f"[RouterNode] 降级 chat: {e}")
        intent = IntentType.CHAT

    logger.info(f"[RouterNode] intent={intent.value}")
    return {**state, "intent_type": intent.value}


async def rag_inventory_node(state: AgentState) -> AgentState:
    """RAG 库存查询节点（仅 inquiry/bargain 触发）"""
    msg = state["latest_msg"]
    logger.info(f"[RAGNode] 查询: {msg[:40]}")
    inv = await asyncio.to_thread(_query_inventory, msg)
    logger.info(f"[RAGNode] {inv}")
    return {**state, "inventory_status": inv}


async def negotiator_node(state: AgentState) -> AgentState:
    """
    谈判回复节点
    inquiry -> 报真实价格（防幻觉）
    bargain -> 守底价，智能让步
    chat    -> 闲聊
    """
    msg    = state["latest_msg"]
    intent = state.get("intent_type", IntentType.CHAT.value)
    inv    = state.get("inventory_status") or {}

    if intent == IntentType.INQUIRY.value:
        if inv.get("found"):
            system = (
                f"你是热情餐厅老板，叫人'兄弟'，不超过35字。\n"
                f"菜品：{inv['item']}，价格：{inv['normal_price']}元，"
                f"库存：{inv['stock']}份。必须报真实价格，不要编造。"
            )
        else:
            system = (
                "你是热情餐厅老板，叫人'兄弟'，不超过35字。\n"
                "没有对应菜品，推荐招牌菜，不要编造价格。"
            )
    elif intent == IntentType.BARGAIN.value:
        if inv.get("found"):
            tip = "库存紧张，坚持原价。" if inv.get("low_stock") else "可小让步但绝不低于底价。"
            system = (
                f"你是精明餐厅老板，叫人'兄弟'，不超过40字。\n"
                f"底价{inv['floor_price']}元（绝不说出），正常{inv['normal_price']}元。\n"
                f"{tip}用话术守住利润。"
            )
        else:
            system = "你是餐厅老板，叫人'兄弟'，价格定死，礼貌拒绝砍价，不超过30字。"
    else:
        system = "你是热情餐厅老板，叫人'兄弟'，随意聊天，不超过30字。"

    try:
        reply = await _call_llm_async(
            [{"role": "system", "content": system},
             {"role": "user",   "content": msg}],
            max_tokens=80,
            temperature=0.7,
        )
    except Exception as e:
        logger.error(f"[NegotiatorNode] LLM 失败: {e}")
        reply = "兄弟，稍等哈，我忙着呢！"

    logger.info(f"[NegotiatorNode] {reply}")

    # 检测成交信号：写入 deal_price 供 PaymentNode 使用
    deal_price = None
    if intent in (IntentType.INQUIRY.value, IntentType.BARGAIN.value) and inv.get("found"):
        DEAL_SIGNALS = ["好的", "行", "就这个", "定了", "要了", "付款", "买了", "扫码",
                        "可以", "成交", "没问题", "OK", "ok", "那就", "来一份", "来两份"]
        if any(sig in msg for sig in DEAL_SIGNALS):
            deal_price = float(inv.get("normal_price") or 0)
            logger.info(f"[NegotiatorNode] 检测到成交信号，price={deal_price}")

    return {**state, "draft_reply": reply, "final_reply": reply,
            "deal_price": deal_price, "payment_triggered": False}


# ==================== 收款节点 ====================

# 全局收款回调（由 lobster_mvp.py 注入）
_payment_callback = None

def set_payment_callback(fn):
    """注入收款触发函数，签名：fn(price: float) -> bool"""
    global _payment_callback
    _payment_callback = fn
    logger.info("[PaymentNode] 收款回调已注入")


async def payment_node(state: AgentState) -> AgentState:
    """
    收款节点：当检测到成交信号时触发收款码发送。
    - 若已注入 _payment_callback，调用设备端发送收款码
    - 若未注入，仅打日志（云端测试模式）
    """
    price = state.get("deal_price") or 0
    if price <= 0:
        # 无成交信号，直接透传
        return {**state, "payment_triggered": False}

    logger.info(f"[PaymentNode] 触发收款，金额={price}元")

    triggered = False
    if _payment_callback:
        try:
            triggered = await asyncio.to_thread(_payment_callback, price)
            if triggered:
                logger.info(f"[PaymentNode] ✅ 收款码已发送，金额={price}元")
            else:
                logger.warning(f"[PaymentNode] ⚠️ 收款码发送失败")
        except Exception as e:
            logger.error(f"[PaymentNode] 发送异常: {e}")
    else:
        logger.info("[PaymentNode] 未注入回调（云端模式），跳过设备操作")
        triggered = True

    # 更新回复：追加收款引导文字
    reply = state.get("final_reply", "")
    if triggered:
        reply = (reply + "\n兄弟，收款码已发给你，扫一下就好！").strip()
    return {**state, "final_reply": reply, "payment_triggered": triggered}


# ==================== 条件路由 ====================

def route_by_intent(state: AgentState) -> str:
    """
    router_node 后的条件边：
    inquiry / bargain  ->  rag
    chat               ->  negotiator
    """
    intent = state.get("intent_type", IntentType.CHAT.value)
    if intent in (IntentType.INQUIRY.value, IntentType.BARGAIN.value):
        return "rag"
    return "negotiator"


# ==================== Graph 编译 ====================

def build_workflow(api_key: str):
    """
    构建并编译商业交易状态机

    流程图：
      [START] -> router
        router --[inquiry/bargain]--> rag -> negotiator -> [END]
        router --[chat]-----------> negotiator -> [END]
    """
    global _API_KEY
    _API_KEY = api_key

    if not _LANGGRAPH_AVAILABLE or StateGraph is None:
        # Railway 云端无 langgraph，使用简化版谈判逻辑
        return _simple_negotiate(state)
    g = StateGraph(AgentState)
    g.add_node("router",     router_node)
    g.add_node("rag",        rag_inventory_node)
    g.add_node("negotiator", negotiator_node)
    g.add_node("payment",    payment_node)

    g.set_entry_point("router")
    g.add_conditional_edges(
        "router",
        route_by_intent,
        {"rag": "rag", "negotiator": "negotiator"},
    )
    g.add_edge("rag",        "negotiator")
    # negotiator -> payment（检测成交信号）-> END
    g.add_edge("negotiator", "payment")
    g.add_edge("payment",    END)

    compiled = g.compile()
    logger.info("✅ AgentWorkflow 编译完成（含 PaymentNode）")
    return compiled


# ==================== 调用接口 ====================

async def run_async(
    workflow,
    user_message: str,
    session_id: str = "default",
) -> str:
    """异步执行，返回 final_reply"""
    state: AgentState = {
        "session_id":        session_id,
        "latest_msg":        user_message,
        "intent_type":       None,
        "inventory_status":  None,
        "draft_reply":       None,
        "final_reply":       None,
        "deal_price":        None,
        "payment_triggered": False,
    }
    try:
        result = await workflow.ainvoke(state)
        return result.get("final_reply") or ""
    except Exception as e:
        logger.error(f"[Workflow] 执行失败: {e}")
        return ""


def run_sync(workflow, user_message: str, session_id: str = "default") -> str:
    """同步包装，适用于非 async 上下文"""
    return asyncio.run(run_async(workflow, user_message, session_id))


# ==================== 完整测试 ====================

class TradeDecision(str, Enum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"


class DarkNetNegotiator:
    """A2A 机器谈判节点：RAG 底价 + DeepSeek(JSON) 决策。"""

    def __init__(self):
        self.store = get_store(
            csv_path=settings.LOCAL_MEMORY_CSV,
            db_dir=settings.LOCAL_MEMORY_DB_DIR,
            top_k=settings.LOCAL_MEMORY_TOP_K,
        )
        self.llm = LLMClient(
            api_key=settings.DEEPSEEK_API_KEY,
            api_url=settings.DEEPSEEK_API_URL,
            model=settings.DEEPSEEK_MODEL,
            temperature=0.1,
            max_tokens=220,
            timeout=settings.DEEPSEEK_TIMEOUT,
            max_retries=settings.DEEPSEEK_MAX_RETRIES,
        )

    def _query_bottom_price(self, item_name: str) -> tuple[float, float]:
        result = self.store.query_business_rules(item_name, top_k=1)
        if result.items:
            top = result.items[0]
            return float(top.floor_price or 0), float(top.price or 0)
        return 0.0, 0.0

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        retry=retry_if_exception_type((requests.exceptions.Timeout, requests.exceptions.ConnectionError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _decide_with_llm(self, item_name: str, expected_price: float, bottom_price: float, normal_price: float) -> dict:
        if not settings.DEEPSEEK_API_KEY:
            return {
                "is_accepted": expected_price >= bottom_price,
                "offered_price": max(bottom_price, min(normal_price, expected_price)),
                "reason": "本地规则报价",
            }
        system = (
            "你是 DarkNetNegotiator。必须仅输出 JSON，不得输出解释。"
            "字段: is_accepted(bool), offered_price(number), reason(string<=32)。"
            "规则: offered_price 必须 > 0；若 expected_price < bottom_price，可拒单。"
        )
        prompt = (
            f"item_name={item_name}; expected_price={expected_price}; "
            f"bottom_price={bottom_price}; normal_price={normal_price}. "
            "请给出严格 JSON。"
        )
        result = self.llm.ask_json(prompt=prompt, system=system)
        if not result:
            raise ValueError("empty llm json result")
        return result

    async def negotiate_intent(self, intent: A2A_TradeIntent, merchant_id: str) -> A2A_MerchantOffer:
        bottom_price, normal_price = await asyncio.to_thread(self._query_bottom_price, intent.item_name)
        if bottom_price <= 0:
            bottom_price = max(1.0, float(intent.expected_price) * 0.75)
        if normal_price <= 0:
            normal_price = max(bottom_price, float(intent.expected_price))

        decision = await asyncio.to_thread(
            self._decide_with_llm,
            intent.item_name,
            float(intent.expected_price),
            float(bottom_price),
            float(normal_price),
        )

        is_accepted = bool(decision.get("is_accepted", False))
        offered_price = float(decision.get("offered_price", normal_price) or normal_price)
        offered_price = max(float(bottom_price), offered_price)
        reason = str(decision.get("reason", "按店规报价"))[:256]

        return A2A_MerchantOffer(
            offer_id=uuid4(),
            intent_id=intent.intent_id,
            merchant_id=merchant_id,
            offered_price=offered_price,
            is_accepted=is_accepted,
            reason=reason,
        )

    async def negotiate_dialogue_turn(
        self,
        *,
        session_id,
        intent_id,
        merchant_id: str,
        item_name: str,
        client_text: str,
        expected_price: float | None,
        round_no: int,
        strategy_hint: str = "",
    ) -> dict:
        target_price = float(expected_price or 0) if expected_price else 0.0
        bottom_price, normal_price = await asyncio.to_thread(self._query_bottom_price, item_name)
        if bottom_price <= 0:
            bottom_price = max(1.0, target_price * 0.75) if target_price > 0 else 8.0
        if normal_price <= 0:
            normal_price = max(bottom_price, target_price or bottom_price)

        decision = await asyncio.to_thread(
            self._decide_with_llm,
            item_name,
            float(target_price or normal_price),
            float(bottom_price),
            float(normal_price),
        )
        offer_price = float(decision.get("offered_price", normal_price) or normal_price)
        offer_price = max(bottom_price, offer_price)

        if strategy_hint:
            hint_text = f"（策略:{strategy_hint[:80]}）"
        else:
            hint_text = ""
        merchant_text = f"第{round_no}轮报价 {offer_price:.1f} 元，{decision.get('reason', '按店规报价')}{hint_text}"

        from shared.claw_protocol import A2A_DialogueTurn, DialogueRole

        turn = A2A_DialogueTurn(
            session_id=session_id,
            intent_id=intent_id,
            round=round_no,
            sender_role=DialogueRole.MERCHANT,
            sender_id=merchant_id,
            receiver_role=DialogueRole.CLIENT,
            receiver_id="client",
            text=merchant_text,
            offered_price=offer_price,
            strategy_hint=strategy_hint[:256],
        )
        return turn.model_dump(mode="json")


async def _run_tests(workflow):
    cases = [
        ("inquiry", "牛肉面多少钱一碗？"),
        ("bargain", "老板麻辣烫能便宜点吗，12块行吧？"),
        ("chat",    "老板你好，最近生意怎么样？"),
        ("unknown", "帮我推荐今天吃什么"),
    ]
    print("\n" + "=" * 60)
    print("🦞 AgentWorkflow 测试开始")
    print("=" * 60)
    for label, msg in cases:
        print(f"\n[{label}] 用户: {msg}")
        reply = await run_async(workflow, msg, session_id=f"test_{label}")
        print(f"[{label}] 龙虾: {reply}")
        print("-" * 40)
    print("\n✅ 全部测试完成")


if __name__ == "__main__":
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stdout,
    )
    try:
        from config import settings
        api_key = settings.DEEPSEEK_API_KEY
    except ImportError:
        api_key = input("请输入 DeepSeek API Key: ").strip()

    wf = build_workflow(api_key=api_key)
    asyncio.run(_run_tests(wf))
