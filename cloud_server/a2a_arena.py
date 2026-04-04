from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Literal, TypedDict

from langgraph.graph import END, StateGraph

_PRICE_RE = re.compile(r"-?\d+(?:\.\d+)?")


class ArenaState(TypedDict, total=False):
    session_id: str
    item_name: str
    buyer_prompt: str
    seller_prompt: str
    seller_bottom_lines: List[str]
    buyer_price: float
    seller_price: float
    turn_count: int
    max_turns: int
    status: str
    judge_decision: str
    transcript: List[Dict[str, Any]]


@dataclass
class DebateEvent:
    session_id: str
    node: str
    thought: str
    action: str
    message: str
    price: float | None
    timestamp: float = field(default_factory=time.time)

    def model_dump(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "node": self.node,
            "thought": self.thought,
            "action": self.action,
            "message": self.message,
            "price": self.price,
            "timestamp": self.timestamp,
        }


class A2AArena:
    """Adversarial Agent Debate arena backed by LangGraph."""

    def __init__(self, llm_client: Any):
        self.llm_client = llm_client
        self.session_history: Dict[str, List[Dict[str, Any]]] = {}
        self.subscribers: Dict[str, List[asyncio.Queue]] = {}
        self.graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(ArenaState)
        graph.add_node("buyer", self._buyer_node)
        graph.add_node("seller", self._seller_node)
        graph.add_node("judge", self._judge_node)
        graph.set_entry_point("buyer")
        graph.add_edge("buyer", "seller")
        graph.add_edge("seller", "judge")
        graph.add_conditional_edges("judge", self._route_after_judge, {
            "agree": END,
            "break": END,
            "failed": END,
            "continue": "buyer",
        })
        return graph.compile()

    async def run(
        self,
        *,
        session_id: str,
        item_name: str,
        buyer_prompt: str,
        seller_prompt: str,
        seller_bottom_lines: List[str],
        buyer_start_price: float,
        seller_start_price: float,
        max_turns: int = 4,
    ) -> Dict[str, Any]:
        self.session_history[session_id] = []
        self.subscribers.setdefault(session_id, [])
        state: ArenaState = {
            "session_id": session_id,
            "item_name": item_name,
            "buyer_prompt": buyer_prompt,
            "seller_prompt": seller_prompt,
            "seller_bottom_lines": list(seller_bottom_lines),
            "buyer_price": float(buyer_start_price),
            "seller_price": float(seller_start_price),
            "turn_count": 0,
            "max_turns": min(max(1, int(max_turns)), 4),
            "status": "active",
            "judge_decision": "continue",
            "transcript": [],
        }
        try:
            result = await self.graph.ainvoke(state)
            await self._publish(session_id, {"type": "done", "payload": dict(result)})
            return dict(result)
        finally:
            await self._publish(session_id, {"type": "close", "payload": {"session_id": session_id}})

    async def stream_events(self, session_id: str) -> AsyncGenerator[Dict[str, Any], None]:
        queue: asyncio.Queue = asyncio.Queue()
        history = list(self.session_history.get(session_id, []))
        subscribers = self.subscribers.setdefault(session_id, [])
        subscribers.append(queue)
        try:
            for item in history:
                yield item
                if item.get("type") == "close":
                    return
            while True:
                item = await queue.get()
                yield item
                if item.get("type") == "close":
                    break
        finally:
            if queue in subscribers:
                subscribers.remove(queue)

    async def _publish(self, session_id: str, item: Dict[str, Any]) -> None:
        history = self.session_history.setdefault(session_id, [])
        history.append(item)
        for queue in list(self.subscribers.get(session_id, [])):
            await queue.put(item)

    async def _buyer_node(self, state: ArenaState) -> ArenaState:
        state["turn_count"] = int(state.get("turn_count", 0)) + 1
        buyer_price = float(state.get("buyer_price", 0.0))
        seller_price = float(state.get("seller_price", buyer_price))
        target_price = round((buyer_price * 0.7 + seller_price * 0.3), 2)
        fallback = {
            "thought": f"当前卖方报价 {seller_price:.2f} 元，我需要继续压价到 {target_price:.2f} 元附近。",
            "action": f"counter_offer:{target_price:.2f}",
            "message": f"我的心理价位是 {target_price:.2f} 元，如果合适我可以尽快成交。",
            "price": target_price,
        }
        data = await self._ask_llm(
            system_prompt=state.get("buyer_prompt", ""),
            user_prompt=(
                f"item_name={state['item_name']}; current_seller_price={seller_price}; "
                f"current_buyer_price={buyer_price}; turn={state['turn_count']}"
            ),
            fallback=fallback,
        )
        state["buyer_price"] = float(data.get("price", target_price) or target_price)
        await self._emit(
            state,
            node="BuyerNode",
            thought=str(data.get("thought", fallback["thought"])),
            action=str(data.get("action", fallback["action"])),
            message=str(data.get("message", fallback["message"])),
            price=state["buyer_price"],
        )
        return state

    async def _seller_node(self, state: ArenaState) -> ArenaState:
        buyer_price = float(state.get("buyer_price", 0.0))
        seller_price = float(state.get("seller_price", buyer_price))
        bottom_candidates = [self._extract_price(x) for x in state.get("seller_bottom_lines", [])]
        bottom_candidates = [x for x in bottom_candidates if x is not None]
        bottom_line = min([seller_price, *bottom_candidates]) if bottom_candidates else seller_price * 0.9
        counter_price = max(round((seller_price * 0.6 + buyer_price * 0.4), 2), round(bottom_line, 2))
        fallback = {
            "thought": f"买方出价 {buyer_price:.2f} 元，我必须守住底线 {bottom_line:.2f} 元。",
            "action": f"counter_offer:{counter_price:.2f}",
            "message": f"我最多只能让到 {counter_price:.2f} 元，再低就没有利润了。",
            "price": counter_price,
        }
        data = await self._ask_llm(
            system_prompt=(
                f"{state.get('seller_prompt', '')}\n"
                f"底线规则：{'；'.join(state.get('seller_bottom_lines', [])) or '无'}"
            ),
            user_prompt=(
                f"item_name={state['item_name']}; buyer_price={buyer_price}; "
                f"current_seller_price={seller_price}; turn={state['turn_count']}"
            ),
            fallback=fallback,
        )
        state["seller_price"] = max(float(data.get("price", counter_price) or counter_price), bottom_line)
        await self._emit(
            state,
            node="SellerNode",
            thought=str(data.get("thought", fallback["thought"])),
            action=str(data.get("action", fallback["action"])),
            message=str(data.get("message", fallback["message"])),
            price=state["seller_price"],
        )
        return state

    async def _judge_node(self, state: ArenaState) -> ArenaState:
        buyer_price = float(state.get("buyer_price", 0.0))
        seller_price = float(state.get("seller_price", 0.0))
        gap = round(abs(seller_price - buyer_price), 2)
        max_turns = int(state.get("max_turns", 4))
        turn_count = int(state.get("turn_count", 0))
        decision = "Agree" if gap < 2 else "Continue"
        if turn_count >= max_turns and decision != "Agree":
            decision = "Break"
        fallback = {
            "thought": f"当前差价 {gap:.2f} 元，我需要裁定是否继续。",
            "action": f"decision:{decision}",
            "message": "双方已经足够接近，可以成交。" if decision == "Agree" else ("谈判已达上限，强制失败。" if decision == "Break" else "继续下一轮谈判。"),
            "decision": decision,
        }
        data = await self._ask_llm(
            system_prompt=(
                "你是 LLM-as-a-Judge。每轮后必须在 Agree / Break / Continue 中三选一。"
                "如果买卖价差 < 2 元，优先 Agree；如果已达到最大轮数且仍未收敛，必须 Break。"
            ),
            user_prompt=f"buyer_price={buyer_price}; seller_price={seller_price}; gap={gap}; turn_count={turn_count}; max_turns={max_turns}",
            fallback=fallback,
        )
        raw_decision = str(data.get("decision", decision)).strip().lower()
        if turn_count >= max_turns and gap >= 2:
            raw_decision = "break"
            state["status"] = "failed"
        elif raw_decision == "agree" or gap < 2:
            raw_decision = "agree"
            state["status"] = "agreed"
        elif raw_decision == "break":
            state["status"] = "failed"
        else:
            raw_decision = "continue"
            state["status"] = "active"
        state["judge_decision"] = raw_decision
        await self._emit(
            state,
            node="JudgeNode",
            thought=str(data.get("thought", fallback["thought"])),
            action=str(data.get("action", f"decision:{raw_decision}")),
            message=str(data.get("message", fallback["message"])),
            price=None,
            extra={"decision": raw_decision, "gap": gap, "status": "SUCCESS" if raw_decision == "agree" else raw_decision.upper()},
        )
        return state

    def _route_after_judge(self, state: ArenaState) -> Literal["agree", "break", "failed", "continue"]:
        decision = str(state.get("judge_decision", "continue")).lower()
        if decision == "agree":
            return "agree"
        if decision == "break":
            return "break"
        if state.get("status") == "failed":
            return "failed"
        return "continue"

    async def _emit(
        self,
        state: ArenaState,
        *,
        node: str,
        thought: str,
        action: str,
        message: str,
        price: float | None,
        extra: Dict[str, Any] | None = None,
    ) -> None:
        event = DebateEvent(
            session_id=str(state["session_id"]),
            node=node,
            thought=thought,
            action=action,
            message=message,
            price=price,
        ).model_dump()
        if extra:
            event.update(extra)
        state.setdefault("transcript", []).append(event)
        await self._publish(str(state["session_id"]), {"type": "node", "payload": event})

    async def _ask_llm(self, *, system_prompt: str, user_prompt: str, fallback: Dict[str, Any]) -> Dict[str, Any]:
        if self.llm_client is None:
            return fallback
        messages = [
            {
                "role": "system",
                "content": (
                    f"{system_prompt}\n"
                    "必须输出 JSON，字段至少包含 thought、action、message，可选 price、decision。"
                ),
            },
            {"role": "user", "content": user_prompt},
        ]
        try:
            if hasattr(self.llm_client, "ask_messages"):
                raw = await asyncio.to_thread(self.llm_client.ask_messages, messages, 0.2)
            elif hasattr(self.llm_client, "chat"):
                raw = await asyncio.to_thread(self.llm_client.chat, messages)
                if raw is not None and hasattr(raw, "content"):
                    raw = raw.content
            else:
                return fallback
            if not raw:
                return fallback
            parsed = self._parse_json(raw)
            return {**fallback, **parsed}
        except Exception:
            return fallback

    def _parse_json(self, raw: str) -> Dict[str, Any]:
        text = (raw or "").strip()
        if "```json" in text:
            text = text.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in text:
            text = text.split("```", 1)[1].split("```", 1)[0].strip()
        try:
            return json.loads(text)
        except Exception:
            price = self._extract_price(text)
            return {"message": text, "price": price}

    def _extract_price(self, text: Any) -> float | None:
        match = _PRICE_RE.search(str(text or ""))
        return float(match.group(0)) if match else None
