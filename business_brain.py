"""
Project Claw v11.0 - 商业大脑状态机

基于 LangGraph 构建纯净的商业对话状态机：

[START]
  └─> intent_router        # 判断意图：点单 / 闲聊 / 投诉 / 退出
        ├─> rag_node         # 意图=点单：检索 ChromaDB 菜品价格
        │     └─> reply_node # 基于 RAG 结果生成防幻觉回复
        ├─> reply_node       # 意图=闲聊：直接 LLM 回复
        └─> reply_node       # 意图=投诉：走安抚流程
[END]
"""
from __future__ import annotations

import logging
import time
from langgraph.graph import StateGraph, END

from llm_client import LLMClient
from brain_rag import RAGEngine

logger = logging.getLogger(__name__)


# ==================== 状态 ====================

class BrainState(dict):
    def __init__(
        self,
        user_message: str = "",
        user_id: str = "anonymous",
        intent: str = "",
        rag_context: str = "",
        final_reply: str = "",
        timestamp: float = 0.0,
        extra: dict = None,
    ):
        super().__init__()
        self["user_message"] = user_message
        self["user_id"]      = user_id
        self["intent"]       = intent
        self["rag_context"]  = rag_context
        self["final_reply"]  = final_reply
        self["timestamp"]    = timestamp or time.time()
        self["extra"]        = extra or {}


# ==================== 节点 ====================

class IntentRouter:
    """意图路由：order / chat / complaint / exit"""

    SYSTEM = (
        "你是餐厅智能助手。判断用户消息意图，"
        "只返回以下之一：order, chat, complaint, exit。"
        "只返回单词，不要解释。"
    )

    def __init__(self, llm: LLMClient):
        self.llm = llm

    def process(self, state: dict) -> dict:
        result = self.llm.ask(state["user_message"], system=self.SYSTEM)
        intent = (result or "chat").strip().lower()
        if intent not in {"order", "chat", "complaint", "exit"}:
            intent = "chat"
        state["intent"] = intent
        logger.info(f"[IntentRouter] {state['user_message'][:30]} -> {intent}")
        return state


class RAGNode:
    """RAG 检索：仅 intent=order 时触发"""

    def __init__(self, rag: RAGEngine):
        self.rag = rag

    def process(self, state: dict) -> dict:
        result = self.rag.query(state["user_message"])
        state["rag_context"] = result.to_context()
        logger.info(f"[RAGNode] {state['rag_context'][:60]}")
        return state


class ReplyNode:
    """回复生成：防幻觉，点单必须基于 RAG 上下文"""

    ORDER_SYS = (
        "你是热情餐厅老板，叫人'兄弟'，回复简短不超过40字。\n"
        "必须严格基于以下菜单，不要编造价格：\n\n{ctx}"
    )
    CHAT_SYS      = "你是热情餐厅老板，叫人'兄弟'，随意闲聊，不超过30字。"
    COMPLAINT_SYS = "你是餐厅老板，顾客有投诉，真诚道歉并承诺改进，叫人'兄弟'，不超过40字。"
    EXIT_SYS      = "你是餐厅老板，顾客离开了，热情道别，叫人'兄弟'，不超过20字。"

    def __init__(self, llm: LLMClient):
        self.llm = llm

    def process(self, state: dict) -> dict:
        intent = state.get("intent", "chat")
        ctx    = state.get("rag_context", "")
        msg    = state["user_message"]

        if intent == "order":
            system = self.ORDER_SYS.format(ctx=ctx)
        elif intent == "complaint":
            system = self.COMPLAINT_SYS
        elif intent == "exit":
            system = self.EXIT_SYS
        else:
            system = self.CHAT_SYS

        reply = self.llm.ask(msg, system=system)
        state["final_reply"] = reply or "兄弟，稍等哈！"
        logger.info(f"[ReplyNode] {state['final_reply']}")
        return state


# ==================== A2A 询价节点 ====================

class A2AQueryNode:
    """
    A2A 后台询价节点：
    - 从 ChromaDB 检索菜品和底价
    - 判断是否亏本（final_price >= floor_price）
    - 生成极简 MerchantOffer 话术
    - 结果写入 state['a2a_offer']（dict）
    """

    OFFER_SYS = (
        "你是餐厅智能销售助手，根据顾客需求和菜单信息，"
        "生成一句极简的报价话术（不超过30字），"
        "必须包含推荐菜品名和最终价格，语气热情自然。\n\n"
        "菜单信息：\n{ctx}\n\n"
        "顾客需求：{demand}"
    )

    def __init__(self, llm: LLMClient, rag: RAGEngine):
        self.llm = llm
        self.rag = rag

    def process(self, state: dict) -> dict:
        demand    = state.get("user_message", "")
        max_price = float(state.get("extra", {}).get("max_price", 9999))

        # 检索 ChromaDB 菜品
        rag_result  = self.rag.query(demand)
        ctx         = rag_result.to_context()
        floor_price = rag_result.floor_price if hasattr(rag_result, "floor_price") else 0.0
        item_price  = rag_result.price       if hasattr(rag_result, "price")       else 0.0
        item_name   = rag_result.item_name   if hasattr(rag_result, "item_name")   else ""

        # 尝试从 context 文本中解析价格（兜底）
        if item_price <= 0:
            import re
            prices = re.findall(r"(\d+\.?\d*)\s*元", ctx)
            item_price  = float(prices[0])  if prices else 15.0
            floor_price = float(prices[-1]) if len(prices) > 1 else item_price * 0.7

        # 底价保护：final_price 不低于 floor_price，不高于 max_price
        final_price = min(max(item_price, floor_price), max_price)

        # 亏本检查
        if final_price < floor_price:
            logger.info(f"[A2AQueryNode] 低于底价 ({final_price}<{floor_price})，拒绝报价")
            state["a2a_offer"] = {"viable": False, "reason": "低于底价"}
            state["final_reply"] = ""
            return state

        if final_price > max_price:
            logger.info(f"[A2AQueryNode] 超出客户预算 ({final_price}>{max_price})，拒绝报价")
            state["a2a_offer"] = {"viable": False, "reason": "超出预算"}
            state["final_reply"] = ""
            return state

        # 生成话术
        reply_text = self.llm.ask(
            demand,
            system=self.OFFER_SYS.format(ctx=ctx, demand=demand),
        ) or f"推荐{item_name or '招牌菜'}，{final_price:.0f}元，欢迎光临！"

        offer = {
            "viable":      True,
            "reply_text":  reply_text,
            "final_price": final_price,
            "floor_price": floor_price,
            "item_name":   item_name,
            "match_score": min(100.0, 60.0 + (max_price - final_price) / max(max_price, 1) * 40),
        }
        state["a2a_offer"]   = offer
        state["final_reply"] = reply_text
        logger.info(f"[A2AQueryNode] offer={offer}")
        return state


# ==================== LangGraph 工作流 ====================

def build_business_brain(
    llm: LLMClient,
    rag: RAGEngine,
):
    """
    构建商业大脑 LangGraph 工作流

    路由：
      intent=order   -> rag_node -> reply_node -> END
      intent=others  -> reply_node -> END

    扩展点（注释标记）：
      # [EXTEND] 可在 rag_node 后插入 ERPSyncNode
      # [EXTEND] 可在 reply_node 后插入 SentimentNode
    """
    router   = IntentRouter(llm)
    rag_nd   = RAGNode(rag)
    reply_nd = ReplyNode(llm)
    a2a_nd   = A2AQueryNode(llm, rag)

    def node_intent(state: dict) -> dict:
        # A2A 后台询价请求，跳过 LLM 意图识别
        if state.get("extra", {}).get("is_a2a"):
            state["intent"] = "a2a"
            return state
        return router.process(state)

    def node_rag(state: dict) -> dict:
        return rag_nd.process(state)

    def node_a2a(state: dict) -> dict:
        return a2a_nd.process(state)

    def node_reply(state: dict) -> dict:
        return reply_nd.process(state)

    def route_by_intent(state: dict) -> str:
        """条件路由：a2a 走 A2AQueryNode，order 走 RAG，其余直接回复"""
        intent = state.get("intent", "chat")
        if intent == "a2a":
            return "a2a"
        return "rag" if intent == "order" else "reply"

    graph = StateGraph(dict)
    graph.add_node("intent", node_intent)
    graph.add_node("rag",    node_rag)
    graph.add_node("a2a",    node_a2a)
    graph.add_node("reply",  node_reply)

    graph.set_entry_point("intent")
    graph.add_conditional_edges(
        "intent",
        route_by_intent,
        {"rag": "rag", "a2a": "a2a", "reply": "reply"},
    )
    graph.add_edge("a2a",  END)   # A2A 询价不需要 ReplyNode
    graph.add_edge("rag",  "reply")
    graph.add_edge("reply", END)

    return graph.compile()


def run_brain(
    workflow,
    user_message: str,
    user_id: str = "anonymous",
) -> str:
    """
    执行商业大脑，返回最终回复字符串
    失败时返回空字符串，由调用方决定降级策略
    """
    state = BrainState(
        user_message=user_message,
        user_id=user_id,
    )
    try:
        result = workflow.invoke(dict(state))
        return result.get("final_reply", "")
    except Exception as e:
        logger.error(f"[BusinessBrain] 工作流执行失败: {e}")
        return ""
