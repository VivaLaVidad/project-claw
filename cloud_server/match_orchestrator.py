from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import random
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from logger_setup import setup_logger


logger = setup_logger("claw.sandbox")

_MENU_NORMAL = {
    "牛肉面": 18.0,
    "麻辣烫": 15.0,
    "水饺": 8.0,
    "炒饭": 12.0,
}

_MENU_FLOOR = {
    "牛肉面": 12.0,
    "麻辣烫": 9.0,
    "水饺": 5.0,
    "炒饭": 8.0,
}


@dataclass
class SandboxRound:
    round_num: int
    buyer_offer: float
    seller_accept: bool
    seller_counter: float
    seller_gift: str
    score: float
    buyer_alias: str
    seller_alias: str
    ts: float = field(default_factory=time.time)


class MatchOrchestrator:
    """匿名 A2A Sandbox + SSE SocialStream 中控。"""

    def __init__(self, hmac_secret: str = ""):
        self.hmac_secret = (hmac_secret or os.getenv("PROJECT_CLAW_A2A_HMAC_SECRET", "claw-a2a-secret")).encode("utf-8")
        self.social_streams: dict[str, list[asyncio.Queue]] = defaultdict(list)

    def obfuscate_id(self, raw_id: str, role: str) -> str:
        raw = f"{role}:{raw_id}".encode("utf-8")
        digest = hmac.new(self.hmac_secret, raw, hashlib.sha256).hexdigest()[:10].upper()
        return f"0x{digest}"

    def _score(self, buyer_offer: float, seller_price: float, gift: str) -> float:
        if seller_price <= 0:
            return 0.0
        gap_ratio = abs(seller_price - buyer_offer) / seller_price
        closeness = max(0.0, 1.0 - gap_ratio)
        gift_bonus = 0.08 if gift else 0.0
        return round(min(1.0, closeness * 0.92 + gift_bonus), 4)

    async def subscribe(self, client_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self.social_streams[client_id].append(q)
        return q

    def unsubscribe(self, client_id: str, queue: asyncio.Queue) -> None:
        queues = self.social_streams.get(client_id, [])
        if queue in queues:
            queues.remove(queue)
        if not queues:
            self.social_streams.pop(client_id, None)

    async def _emit(self, client_id: str, event: dict[str, Any]) -> None:
        for q in list(self.social_streams.get(client_id, [])):
            await q.put(event)

    async def _default_seller_mas_eval(self, item: str, buyer_offer: float, round_num: int) -> dict[str, Any]:
        normal = _MENU_NORMAL.get(item, 18.0)
        floor = _MENU_FLOOR.get(item, max(8.0, normal * 0.65))
        concession = 0.6 * (round_num - 1)
        counter = round(max(floor, normal - concession), 1)
        accept = buyer_offer >= counter
        gift = "煎蛋" if item == "牛肉面" and not accept else ("可乐" if buyer_offer >= counter - 0.5 else "")
        return {"accept": accept, "counter": counter, "gift": gift, "floor": floor, "normal": normal}

    async def run_sandbox(
        self,
        client_id: str,
        merchant_id: str,
        buyer_payload: dict[str, Any],
        seller_eval: Optional[Callable[[str, float, int], Awaitable[dict[str, Any]]]] = None,
    ) -> dict[str, Any]:
        item = str(buyer_payload.get("item", "")).strip() or "牛肉面"
        buyer_offer = float(buyer_payload.get("target", 0) or 0)
        request_id = uuid.uuid4().hex[:12]
        buyer_alias = self.obfuscate_id(client_id, "buyer")
        seller_alias = self.obfuscate_id(merchant_id, "seller")
        seller_eval = seller_eval or self._default_seller_mas_eval
        rounds: list[SandboxRound] = []
        agreement: dict[str, Any] | None = None

        for round_num in range(1, 4):
            seller_reply = await seller_eval(item, buyer_offer, round_num)
            accept = bool(seller_reply.get("accept", False))
            counter = float(seller_reply.get("counter", 0.0) or 0.0)
            gift = str(seller_reply.get("gift", "")).strip()
            score = self._score(buyer_offer, counter or buyer_offer, gift)
            rounds.append(SandboxRound(
                round_num=round_num,
                buyer_offer=buyer_offer,
                seller_accept=accept,
                seller_counter=counter,
                seller_gift=gift,
                score=score,
                buyer_alias=buyer_alias,
                seller_alias=seller_alias,
            ))
            if accept:
                agreement = {
                    "request_id": request_id,
                    "item": item,
                    "agreed_price": buyer_offer,
                    "gift": gift,
                    "buyer_alias": buyer_alias,
                    "seller_alias": seller_alias,
                    "score": score,
                    "agreement": True,
                }
                break
            if score >= 0.85:
                agreement = {
                    "request_id": request_id,
                    "item": item,
                    "agreed_price": counter,
                    "gift": gift,
                    "buyer_alias": buyer_alias,
                    "seller_alias": seller_alias,
                    "score": score,
                    "agreement": False,
                    "recommended": True,
                }
                break
            buyer_offer = round((buyer_offer + counter) / 2, 1)

        transcript = [
            {
                "round": r.round_num,
                "buyer": {"alias": r.buyer_alias, "offer": r.buyer_offer},
                "seller": {"alias": r.seller_alias, "accept": r.seller_accept, "counter": r.seller_counter, "gift": r.seller_gift},
                "score": r.score,
                "ts": r.ts,
            }
            for r in rounds
        ]
        result = {
            "request_id": request_id,
            "client_alias": buyer_alias,
            "merchant_alias": seller_alias,
            "item": item,
            "rounds": transcript,
            "final": agreement,
            "emitted": False,
        }
        if agreement:
            logger.a2a_handshake(f"agreement:{buyer_alias}->{seller_alias}:{item}:{agreement.get('agreed_price')}")
            await self._emit(client_id, {"event": "sandbox_result", "data": result})
            result["emitted"] = True
        return result

    async def stream_events(self, client_id: str):
        queue = await self.subscribe(client_id)
        try:
            while True:
                event = await queue.get()
                yield f"event: {event.get('event', 'message')}\n"
                yield f"data: {json.dumps(event.get('data', {}), ensure_ascii=False)}\n\n"
        finally:
            self.unsubscribe(client_id, queue)
