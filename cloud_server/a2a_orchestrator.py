from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from fastapi import WebSocket

from logger_setup import setup_logger
from shared.claw_protocol import A2A_MerchantOffer, A2A_TradeDecision, A2A_TradeIntent


logger = setup_logger("claw.a2a.arena")


@dataclass
class MerchantSession:
    merchant_id: str
    ws: WebSocket
    distance_km: float = 0.0
    last_seen: float = field(default_factory=time.time)
    alive: bool = True


@dataclass
class RankedOffer:
    offer: A2A_MerchantOffer
    distance_km: float
    price_score: float
    distance_score: float
    total_score: float


class TradeArena:
    """高并发 A2A 撮合引擎（WebSocket 广播 + 超时收集 + Top-K 回推）。"""

    def __init__(self, timeout_seconds: float = 3.0, top_k: int = 3):
        self.timeout_seconds = timeout_seconds
        self.top_k = top_k

        self._merchant_lock = asyncio.Lock()
        self._client_lock = asyncio.Lock()

        self._merchants: dict[str, MerchantSession] = {}
        self._client_ws: dict[str, WebSocket] = {}
        self._client_sse: dict[str, list[asyncio.Queue]] = defaultdict(list)

        self._pending_offers: dict[str, list[A2A_MerchantOffer]] = defaultdict(list)
        self._pending_events: dict[str, asyncio.Event] = {}
        self._offer_to_merchant: dict[str, str] = {}

    async def register_merchant(self, merchant_id: str, ws: WebSocket, distance_km: float = 0.0) -> None:
        await ws.accept()
        async with self._merchant_lock:
            self._merchants[merchant_id] = MerchantSession(merchant_id=merchant_id, ws=ws, distance_km=max(0.0, float(distance_km)))
        logger.info(f"[TradeArena] merchant online={merchant_id} total={len(self._merchants)}")

    async def unregister_merchant(self, merchant_id: str) -> None:
        async with self._merchant_lock:
            self._merchants.pop(merchant_id, None)
        logger.info(f"[TradeArena] merchant offline={merchant_id} total={len(self._merchants)}")

    async def register_client_ws(self, client_id: str, ws: WebSocket) -> None:
        await ws.accept()
        async with self._client_lock:
            self._client_ws[client_id] = ws
        logger.info(f"[TradeArena] client ws online={client_id}")

    async def unregister_client_ws(self, client_id: str) -> None:
        async with self._client_lock:
            self._client_ws.pop(client_id, None)
        logger.info(f"[TradeArena] client ws offline={client_id}")

    async def subscribe_client_sse(self, client_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._client_sse[client_id].append(q)
        return q

    def unsubscribe_client_sse(self, client_id: str, queue: asyncio.Queue) -> None:
        queues = self._client_sse.get(client_id, [])
        if queue in queues:
            queues.remove(queue)
        if not queues:
            self._client_sse.pop(client_id, None)

    async def stream_client_events(self, client_id: str):
        q = await self.subscribe_client_sse(client_id)
        try:
            while True:
                event = await q.get()
                yield f"event: {event.get('event', 'message')}\n"
                yield f"data: {json.dumps(event.get('data', {}), ensure_ascii=False)}\n\n"
        finally:
            self.unsubscribe_client_sse(client_id, q)

    async def submit_intent(self, intent: A2A_TradeIntent) -> dict[str, Any]:
        intent_key = str(intent.intent_id)
        eligible_merchants = await self._get_eligible_merchants(intent.max_distance_km)

        self._pending_offers[intent_key] = []
        self._pending_events[intent_key] = asyncio.Event()

        logger.info(
            f"[TradeArena] intent={intent_key[:8]} client={intent.client_id} eligible={len(eligible_merchants)} timeout={self.timeout_seconds}s"
        )

        payload = {
            "type": "a2a_trade_intent",
            "intent": intent.model_dump(mode="json"),
        }

        await asyncio.gather(
            *[self._safe_send_to_merchant(session, payload) for session in eligible_merchants],
            return_exceptions=True,
        )

        try:
            await asyncio.wait_for(
                self._wait_offer_window(intent_key=intent_key, expected_count=len(eligible_merchants)),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.info(f"[TradeArena] intent={intent_key[:8]} wait window timeout")
        except Exception as e:  # noqa: BLE001
            logger.exception(f"[TradeArena] intent={intent_key[:8]} wait window error: {e}")

        offers = self._pending_offers.pop(intent_key, [])
        self._pending_events.pop(intent_key, None)

        ranked = self._rank_offers(offers, eligible_merchants)
        top_ranked = ranked[: self.top_k]
        top_payload = [
            {
                **r.offer.model_dump(mode="json"),
                "distance_km": r.distance_km,
                "price_score": round(r.price_score, 4),
                "distance_score": round(r.distance_score, 4),
                "total_score": round(r.total_score, 4),
            }
            for r in top_ranked
        ]

        await self._push_result_to_client(
            client_id=intent.client_id,
            intent_id=intent_key,
            offers=top_payload,
            responded=len(offers),
            candidate_count=len(eligible_merchants),
        )

        return {
            "intent_id": intent_key,
            "client_id": intent.client_id,
            "responded": len(offers),
            "candidate_count": len(eligible_merchants),
            "offers": top_payload,
            "timeout_seconds": self.timeout_seconds,
        }

    async def on_merchant_offer(self, offer: A2A_MerchantOffer) -> None:
        intent_key = str(offer.intent_id)
        if intent_key not in self._pending_offers:
            logger.warning(f"[TradeArena] offer dropped, unknown/expired intent={intent_key[:8]}")
            return
        self._pending_offers[intent_key].append(offer)
        self._offer_to_merchant[str(offer.offer_id)] = offer.merchant_id
        evt = self._pending_events.get(intent_key)
        if evt is not None:
            evt.set()

    async def dispatch_trade_decision(self, decision: A2A_TradeDecision, final_price: float = 0.0) -> dict[str, Any]:
        merchant_id = self._offer_to_merchant.get(str(decision.offer_id), "")
        if not merchant_id:
            raise ValueError("merchant not found for offer_id")

        async with self._merchant_lock:
            session = self._merchants.get(merchant_id)
        if session is None or not session.alive:
            raise ValueError("merchant offline")

        payload = {
            "type": "a2a_trade_decision",
            "decision": decision.model_dump(mode="json"),
            "final_price": float(final_price),
            "ts": time.time(),
        }
        await session.ws.send_text(json.dumps(payload, ensure_ascii=False))
        return {"ok": True, "merchant_id": merchant_id, "offer_id": str(decision.offer_id), "decision": decision.decision}

    async def _get_eligible_merchants(self, max_distance_km: float) -> list[MerchantSession]:
        async with self._merchant_lock:
            merchants = list(self._merchants.values())
        return [m for m in merchants if m.alive and m.distance_km <= float(max_distance_km)]

    async def _safe_send_to_merchant(self, session: MerchantSession, payload: dict[str, Any]) -> None:
        try:
            await session.ws.send_text(json.dumps(payload, ensure_ascii=False))
            session.last_seen = time.time()
        except Exception as e:  # noqa: BLE001
            session.alive = False
            logger.warning(f"[TradeArena] send merchant failed id={session.merchant_id} err={e}")

    async def _wait_offer_window(self, intent_key: str, expected_count: int) -> None:
        if expected_count <= 0:
            return
        evt = self._pending_events[intent_key]
        while True:
            if len(self._pending_offers.get(intent_key, [])) >= expected_count:
                return
            evt.clear()
            await evt.wait()

    def _rank_offers(self, offers: list[A2A_MerchantOffer], merchants: list[MerchantSession]) -> list[RankedOffer]:
        if not offers:
            return []

        distance_map = {m.merchant_id: m.distance_km for m in merchants}
        min_price = min(o.offered_price for o in offers)
        max_price = max(o.offered_price for o in offers)
        price_span = max(0.0001, max_price - min_price)

        ranked: list[RankedOffer] = []
        for offer in offers:
            dist = float(distance_map.get(offer.merchant_id, 999.0))
            price_score = 1.0 - ((offer.offered_price - min_price) / price_span)
            distance_score = 1.0 / (1.0 + dist)
            total_score = 0.75 * price_score + 0.25 * distance_score
            ranked.append(
                RankedOffer(
                    offer=offer,
                    distance_km=dist,
                    price_score=price_score,
                    distance_score=distance_score,
                    total_score=total_score,
                )
            )

        ranked.sort(key=lambda x: (x.offer.offered_price, -x.total_score))
        return ranked

    async def _push_result_to_client(
        self,
        client_id: str,
        intent_id: str,
        offers: list[dict[str, Any]],
        responded: int,
        candidate_count: int,
    ) -> None:
        payload = {
            "type": "a2a_trade_result",
            "intent_id": intent_id,
            "offers": offers,
            "responded": responded,
            "candidate_count": candidate_count,
            "ts": time.time(),
        }

        ws = self._client_ws.get(client_id)
        if ws is not None:
            try:
                await ws.send_text(json.dumps(payload, ensure_ascii=False))
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[TradeArena] push ws failed client={client_id} err={e}")

        queues = list(self._client_sse.get(client_id, []))
        for q in queues:
            try:
                await q.put({"event": "a2a_trade_result", "data": payload})
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[TradeArena] push sse failed client={client_id} err={e}")


def parse_offer_message(raw_text: str) -> A2A_MerchantOffer:
    data = json.loads(raw_text)
    if data.get("type") == "a2a_merchant_offer":
        data = data.get("offer", {})
    return A2A_MerchantOffer.model_validate(data)


def parse_intent_message(raw_text: str) -> A2A_TradeIntent:
    data = json.loads(raw_text)
    if data.get("type") == "a2a_trade_intent":
        data = data.get("intent", {})
    if "intent_id" in data and isinstance(data["intent_id"], UUID):
        data["intent_id"] = str(data["intent_id"])
    return A2A_TradeIntent.model_validate(data)
