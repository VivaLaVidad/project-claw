from __future__ import annotations

"""cloud_server/agent_workflow.py
B 端商业博弈多智能体状态机（LangGraph）

节点：
- InventoryNode: ChromaDB RAG 拉取底价/库存
- StrategyNode: 动态效用（闲时 1.05x，峰时 1.3x）
- NegotiatorNode: 调用本地 vLLM，强制 JSON 输出
- CriticNode: 风控校验，低于底价触发 PolicyViolation 并重试路由
"""

import json
import os
import re
from datetime import datetime
from typing import Any, Optional, TypedDict, Literal

import httpx

from langgraph.graph import END, StateGraph

try:
    import chromadb
except Exception:  # pragma: no cover
    chromadb = None


class PolicyViolation(RuntimeError):
    pass


class MerchantState(TypedDict, total=False):
    # 用户与商家输入
    request_id: str
    merchant_id: str
    item_name: str
    user_offer: float
    current_traffic: float

    # RAG/策略推导
    bottom_price: float
    inventory: int
    strategy_min_accept: float
    strategy_note: str

    # 谈判产物
    thought: str
    quote_text: str
    final_offer: float

    # 控制字段
    retry_count: int
    max_retries: int
    critic_error: str


class InventoryNode:
    def __init__(self, chroma_path: str = "./.chroma", collection_name: str = "merchant_inventory"):
        self.chroma_path = chroma_path
        self.collection_name = collection_name

    def _fallback_inventory(self, state: MerchantState) -> dict[str, Any]:
        # 兜底（确保系统可运行）
        return {
            "bottom_price": 18.0,
            "inventory": 20,
            "current_traffic": state.get("current_traffic", 0.5),
        }

    def __call__(self, state: MerchantState) -> MerchantState:
        if chromadb is None:
            data = self._fallback_inventory(state)
            return {**state, **data}

        client = chromadb.PersistentClient(path=self.chroma_path)
        collection = client.get_or_create_collection(self.collection_name)

        query = f"merchant={state.get('merchant_id','')} item={state.get('item_name','')}"
        res = collection.query(query_texts=[query], n_results=1)

        if not res.get("metadatas") or not res["metadatas"][0]:
            data = self._fallback_inventory(state)
            return {**state, **data}

        md = res["metadatas"][0][0] or {}
        bottom_price = float(md.get("bottom_price", 18.0))
        inventory = int(md.get("inventory", 20))
        traffic = float(md.get("current_traffic", state.get("current_traffic", 0.5)))

        return {
            **state,
            "bottom_price": bottom_price,
            "inventory": inventory,
            "current_traffic": traffic,
        }


class StrategyNode:
    def __call__(self, state: MerchantState) -> MerchantState:
        bottom = float(state.get("bottom_price", 0.0))
        hour = datetime.now().hour

        # 闲时：15点附近 + traffic 低；峰时：高 traffic 或饭点
        is_off_peak = (hour == 15) or (14 <= hour <= 16 and float(state.get("current_traffic", 0.0)) < 0.45)
        is_peak = float(state.get("current_traffic", 0.0)) >= 0.75 or (11 <= hour <= 13) or (18 <= hour <= 20)

        if is_off_peak and not is_peak:
            min_accept = round(bottom * 1.05, 2)
            note = "闲时微利策略：可接受 1.05x 底价"
        else:
            min_accept = round(bottom * 1.30, 2)
            note = "高峰利润策略：坚守 1.3x 底价"

        return {**state, "strategy_min_accept": min_accept, "strategy_note": note}


class NegotiatorNode:
    def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None, timeout_sec: float = 12.0):
        self.base_url = base_url or os.getenv("VLLM_BASE_URL", "http://127.0.0.1:8000")
        self.model = model or os.getenv("VLLM_MODEL", "Qwen-2.5-32B-Instruct")
        self.timeout_sec = timeout_sec

    async def __call__(self, state: MerchantState) -> MerchantState:
        user_offer = float(state.get("user_offer", 0.0))
        min_accept = float(state.get("strategy_min_accept", 0.0))
        bottom = float(state.get("bottom_price", 0.0))

        system_prompt = (
            "你是资深销售谈判专家。必须仅输出 JSON，不得输出任何额外文字。\n"
            "JSON schema: {\"thought\":str, \"quote_text\":str, \"final_offer\":number}\n"
            f"硬约束：final_offer >= {bottom} 且优先 >= {min_accept}。"
        )
        user_prompt = (
            f"用户出价={user_offer}；底价={bottom}；策略最低可接受={min_accept}；"
            "请输出面向用户的讨价还价话术和最终报价。"
        )

        payload = {
            "model": self.model,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
            resp = await client.post(f"{self.base_url}/v1/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()

        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        final_offer = float(parsed.get("final_offer", min_accept))

        return {
            **state,
            "thought": str(parsed.get("thought", "正在综合库存与时段策略议价...")),
            "quote_text": str(parsed.get("quote_text", "老板给你最优报价了")),
            "final_offer": round(final_offer, 2),
        }


class CriticNode:
    _price_pattern = re.compile(r"-?\d+(?:\.\d+)?")

    def __call__(self, state: MerchantState) -> MerchantState:
        bottom = float(state.get("bottom_price", 0.0))
        offered = state.get("final_offer")

        if offered is None:
            txt = str(state.get("quote_text", ""))
            m = self._price_pattern.search(txt)
            offered = float(m.group(0)) if m else -1

        if float(offered) < bottom:
            raise PolicyViolation(f"offer {offered} below bottom_price {bottom}")

        return {**state, "critic_error": ""}


def _route_after_critic(state: MerchantState) -> Literal["success", "retry", "failed"]:
    if state.get("critic_error"):
        if int(state.get("retry_count", 0)) < int(state.get("max_retries", 2)):
            return "retry"
        return "failed"
    return "success"


async def _critic_guard(state: MerchantState, critic: CriticNode) -> MerchantState:
    try:
        return critic(state)
    except PolicyViolation as e:
        return {
            **state,
            "critic_error": str(e),
            "retry_count": int(state.get("retry_count", 0)) + 1,
            "final_offer": max(float(state.get("bottom_price", 0.0)), float(state.get("strategy_min_accept", 0.0))),
            "quote_text": "刚刚重新核算了成本，我给你一个合规且更优的报价。",
            "thought": "风控触发，自动纠偏重试中...",
        }


def build_merchant_graph() -> Any:
    inventory = InventoryNode(
        chroma_path=os.getenv("CHROMA_PATH", "./.chroma"),
        collection_name=os.getenv("CHROMA_COLLECTION", "merchant_inventory"),
    )
    strategy = StrategyNode()
    negotiator = NegotiatorNode()
    critic = CriticNode()

    graph = StateGraph(MerchantState)
    graph.add_node("inventory", inventory)
    graph.add_node("strategy", strategy)
    graph.add_node("negotiator", negotiator)
    graph.add_node("critic", lambda s: _critic_guard(s, critic))

    graph.set_entry_point("inventory")
    graph.add_edge("inventory", "strategy")
    graph.add_edge("strategy", "negotiator")
    graph.add_edge("negotiator", "critic")

    graph.add_conditional_edges(
        "critic",
        _route_after_critic,
        {
            "retry": "negotiator",
            "success": END,
            "failed": END,
        },
    )
    return graph.compile()


async def run_merchant_workflow(
    merchant_id: str,
    item_name: str,
    user_offer: float,
    request_id: Optional[str] = None,
    current_traffic: float = 0.5,
) -> MerchantState:
    app = build_merchant_graph()
    init_state: MerchantState = {
        "request_id": request_id or uuid.uuid4().hex,
        "merchant_id": merchant_id,
        "item_name": item_name,
        "user_offer": float(user_offer),
        "current_traffic": float(current_traffic),
        "retry_count": 0,
        "max_retries": 2,
    }
    out: MerchantState = await app.ainvoke(init_state)
    return out
