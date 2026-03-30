from __future__ import annotations

"""cloud_server/agent_workflow.py
低资源环境友好的 B 端商业博弈状态机（LangGraph + ChromaDB + DeepSeek REST）
"""

import json
import os
import re
import uuid
from datetime import datetime
from typing import Any, Literal, Optional, TypedDict

import httpx
from langgraph.graph import END, StateGraph

try:
    import chromadb
except Exception:  # pragma: no cover
    chromadb = None


class PolicyViolation(RuntimeError):
    pass


class MerchantState(TypedDict, total=False):
    request_id: str
    merchant_id: str
    item_name: str
    user_offer: float
    current_traffic: float

    bottom_price: float
    inventory: int
    strategy_min_accept: float
    strategy_note: str

    thought: str
    quote_text: str
    final_offer: float

    retry_count: int
    max_retries: int
    critic_error: str


class InventoryNode:
    def __init__(self, chroma_path: str = "./.chroma", collection_name: str = "merchant_inventory"):
        self.chroma_path = chroma_path
        self.collection_name = collection_name

    def _fallback(self, state: MerchantState) -> dict[str, Any]:
        return {
            "bottom_price": 18.0,
            "inventory": 20,
            "current_traffic": float(state.get("current_traffic", 0.5)),
        }

    def __call__(self, state: MerchantState) -> MerchantState:
        if chromadb is None:
            return {**state, **self._fallback(state)}

        client = chromadb.PersistentClient(path=self.chroma_path)
        collection = client.get_or_create_collection(self.collection_name)
        query = f"merchant={state.get('merchant_id','')} item={state.get('item_name','')}"
        res = collection.query(query_texts=[query], n_results=1)

        if not res.get("metadatas") or not res["metadatas"][0]:
            return {**state, **self._fallback(state)}

        md = res["metadatas"][0][0] or {}
        return {
            **state,
            "bottom_price": float(md.get("bottom_price", 18.0)),
            "inventory": int(md.get("inventory", 20)),
            "current_traffic": float(md.get("current_traffic", state.get("current_traffic", 0.5))),
        }


class StrategyNode:
    def __call__(self, state: MerchantState) -> MerchantState:
        bottom = float(state.get("bottom_price", 0.0))
        hour = datetime.now().hour
        traffic = float(state.get("current_traffic", 0.0))

        is_off_peak = (hour == 15) or (14 <= hour <= 16 and traffic < 0.45)
        is_peak = traffic >= 0.75 or (11 <= hour <= 13) or (18 <= hour <= 20)

        if is_off_peak and not is_peak:
            min_accept = round(bottom * 1.05, 2)
            note = "闲时微利策略：接受 bottom_price * 1.05"
        else:
            min_accept = round(bottom * 1.30, 2)
            note = "高峰利润策略：坚守 bottom_price * 1.3"

        return {**state, "strategy_min_accept": min_accept, "strategy_note": note}


class NegotiatorNode:
    """强制走外部 DeepSeek REST，严禁本地权重推理。"""

    def __init__(self, timeout_sec: float = 15.0):
        self.base_url = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com")
        self.model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        self.api_key = os.getenv("DEEPSEEK_API_KEY", "")
        self.timeout_sec = timeout_sec

    async def __call__(self, state: MerchantState) -> MerchantState:
        if not self.api_key:
            # 无 key 时返回可运行兜底，方便低配本地联调
            floor = max(float(state.get("bottom_price", 0.0)), float(state.get("strategy_min_accept", 0.0)))
            return {
                **state,
                "thought": "DeepSeek 未配置，使用规则引擎兜底。",
                "quote_text": f"老板给到你当前最优价 {floor:.2f} 元，量大可再谈。",
                "final_offer": floor,
            }

        user_offer = float(state.get("user_offer", 0.0))
        bottom = float(state.get("bottom_price", 0.0))
        min_accept = float(state.get("strategy_min_accept", 0.0))

        system_prompt = (
            "你是商业谈判助手。必须仅输出 JSON，不要 markdown。"
            "schema={\"thought\":str,\"quote_text\":str,\"final_offer\":number}。"
            f"硬约束：final_offer >= {bottom}；策略目标 >= {min_accept}。"
        )
        user_prompt = (
            f"user_offer={user_offer}, bottom_price={bottom}, strategy_min={min_accept}, "
            f"traffic={state.get('current_traffic', 0.5)}"
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
            resp = await client.post(
                f"{self.base_url.rstrip('/')}/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        final_offer = float(parsed.get("final_offer", min_accept))

        return {
            **state,
            "thought": str(parsed.get("thought", "正在博弈最优解...")),
            "quote_text": str(parsed.get("quote_text", "这是当前可执行报价。")),
            "final_offer": round(final_offer, 2),
        }


class CriticNode:
    _price_pattern = re.compile(r"-?\d+(?:\.\d+)?")

    def __call__(self, state: MerchantState) -> MerchantState:
        bottom = float(state.get("bottom_price", 0.0))
        offered = state.get("final_offer")

        if offered is None:
            m = self._price_pattern.search(str(state.get("quote_text", "")))
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
            "quote_text": "风控已触发，已为你切换到合规报价。",
            "thought": "Risk critic reroute：重试中。",
        }


def build_merchant_graph() -> Any:
    graph = StateGraph(MerchantState)
    critic = CriticNode()

    graph.add_node("inventory", InventoryNode(
        chroma_path=os.getenv("CHROMA_PATH", "./.chroma"),
        collection_name=os.getenv("CHROMA_COLLECTION", "merchant_inventory"),
    ))
    graph.add_node("strategy", StrategyNode())
    graph.add_node("negotiator", NegotiatorNode())
    graph.add_node("critic", lambda s: _critic_guard(s, critic))

    graph.set_entry_point("inventory")
    graph.add_edge("inventory", "strategy")
    graph.add_edge("strategy", "negotiator")
    graph.add_edge("negotiator", "critic")
    graph.add_conditional_edges("critic", _route_after_critic, {
        "retry": "negotiator",
        "success": END,
        "failed": END,
    })
    return graph.compile()


async def run_merchant_workflow(
    merchant_id: str,
    item_name: str,
    user_offer: float,
    request_id: Optional[str] = None,
    current_traffic: float = 0.5,
) -> MerchantState:
    app = build_merchant_graph()
    state: MerchantState = {
        "request_id": request_id or uuid.uuid4().hex,
        "merchant_id": merchant_id,
        "item_name": item_name,
        "user_offer": float(user_offer),
        "current_traffic": float(current_traffic),
        "retry_count": 0,
        "max_retries": 2,
    }
    return await app.ainvoke(state)
