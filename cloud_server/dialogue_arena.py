from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from fastapi import WebSocket

from agent_personalization import ClientProfile, MerchantProfile, PersonalizationEngine
from logger_setup import setup_logger
from shared.claw_protocol import (
    A2A_ClientTurnRequest,
    A2A_DialogueSession,
    A2A_DialogueSessionView,
    A2A_DialogueTurn,
    A2A_StartDialogueRequest,
    DialogueRole,
    DialogueSessionStatus,
)


logger = setup_logger("claw.a2a.dialogue")


@dataclass
class DialogueRuntime:
    session: A2A_DialogueSession
    turns: list[A2A_DialogueTurn] = field(default_factory=list)


class DialogueArena:
    """B/C 多轮对话编排（会话状态 + 转发 + OpenMAIC 策略提示 + 个性化画像）。"""

    def __init__(self):
        self._lock = asyncio.Lock()
        self._sessions: dict[str, DialogueRuntime] = {}
        self._client_ws: dict[str, WebSocket] = {}
        self._merchant_ws: dict[str, WebSocket] = {}
        self.personalization = PersonalizationEngine()

        self._openmaic = None
        try:
            from openmaic_adapter import OpenMAICAdapter

            self._openmaic = OpenMAICAdapter()
        except Exception as e:  # noqa: BLE001
            logger.info(f"[DialogueArena] OpenMAIC disabled: {e}")

    async def register_client_ws(self, client_id: str, ws: WebSocket) -> None:
        async with self._lock:
            self._client_ws[client_id] = ws

    async def unregister_client_ws(self, client_id: str) -> None:
        async with self._lock:
            self._client_ws.pop(client_id, None)

    async def register_merchant_ws(self, merchant_id: str, ws: WebSocket) -> None:
        async with self._lock:
            self._merchant_ws[merchant_id] = ws

    async def unregister_merchant_ws(self, merchant_id: str) -> None:
        async with self._lock:
            self._merchant_ws.pop(merchant_id, None)

    async def upsert_client_profile(self, profile: dict[str, Any]) -> dict[str, Any]:
        p = ClientProfile(
            client_id=str(profile.get("client_id", "")),
            budget_min=float(profile.get("budget_min", 10.0)),
            budget_max=float(profile.get("budget_max", 50.0)),
            price_sensitivity=float(profile.get("price_sensitivity", 0.8)),
            time_urgency=float(profile.get("time_urgency", 0.5)),
            quality_preference=float(profile.get("quality_preference", 0.6)),
            custom_tags=list(profile.get("custom_tags", []) or []),
        )
        self.personalization.register_client(p)
        return p.to_dict()

    async def upsert_merchant_profile(self, profile: dict[str, Any]) -> dict[str, Any]:
        p = MerchantProfile(
            merchant_id=str(profile.get("merchant_id", "")),
            bottom_price=float(profile.get("bottom_price", 8.0)),
            normal_price=float(profile.get("normal_price", 15.0)),
            max_discount_rate=float(profile.get("max_discount_rate", 0.15)),
            delivery_time_minutes=int(profile.get("delivery_time_minutes", 15)),
            quality_score=float(profile.get("quality_score", 0.85)),
            service_score=float(profile.get("service_score", 0.80)),
            inventory_status=dict(profile.get("inventory_status", {}) or {}),
            custom_tags=list(profile.get("custom_tags", []) or []),
        )
        self.personalization.register_merchant(p)
        return p.to_dict()

    async def start_dialogue(self, req: A2A_StartDialogueRequest) -> dict[str, Any]:
        now = time.time()
        session = A2A_DialogueSession(
            intent_id=req.intent.intent_id,
            client_id=req.intent.client_id,
            merchant_id=req.merchant_id,
            item_name=req.intent.item_name,
            status=DialogueSessionStatus.OPEN,
            round=1,
            created_at=now,
            updated_at=now,
        )

        strategy_hint = await self._strategy_hint(req.opening_text, req.intent.item_name)
        first_turn = A2A_DialogueTurn(
            session_id=session.session_id,
            intent_id=req.intent.intent_id,
            round=1,
            sender_role=DialogueRole.CLIENT,
            sender_id=req.intent.client_id,
            receiver_role=DialogueRole.MERCHANT,
            receiver_id=req.merchant_id,
            text=req.opening_text,
            expected_price=req.intent.expected_price,
            strategy_hint=strategy_hint,
        )

        async with self._lock:
            self._sessions[str(session.session_id)] = DialogueRuntime(session=session, turns=[first_turn])

        await self._push_to_merchant(req.merchant_id, first_turn)
        await self._push_to_client(req.intent.client_id, first_turn)
        return {"session_id": str(session.session_id), "status": session.status, "round": session.round}

    async def client_turn(self, req: A2A_ClientTurnRequest) -> dict[str, Any]:
        session_id = str(req.session_id)
        async with self._lock:
            runtime = self._sessions.get(session_id)
        if runtime is None:
            raise ValueError("session not found")
        if runtime.session.status != DialogueSessionStatus.OPEN:
            raise ValueError("session closed")
        if runtime.session.client_id != req.client_id:
            raise ValueError("client mismatch")

        runtime.session.round += 1
        runtime.session.updated_at = time.time()

        suggested = self.personalization.suggest_next_offer(
            merchant_id=runtime.session.merchant_id,
            client_id=req.client_id,
            current_round=runtime.session.round,
            client_expected_price=float(req.expected_price or 0),
        )
        strategy_hint = await self._strategy_hint(req.text, runtime.session.item_name)
        merged_hint = f"{strategy_hint}; suggest_price={suggested.get('suggested_price', '-')}; {suggested.get('reason', '')}"[:256]

        turn = A2A_DialogueTurn(
            session_id=runtime.session.session_id,
            intent_id=runtime.session.intent_id,
            round=runtime.session.round,
            sender_role=DialogueRole.CLIENT,
            sender_id=req.client_id,
            receiver_role=DialogueRole.MERCHANT,
            receiver_id=runtime.session.merchant_id,
            text=req.text,
            expected_price=req.expected_price,
            strategy_hint=merged_hint,
        )
        runtime.turns.append(turn)
        await self._push_to_merchant(runtime.session.merchant_id, turn)
        await self._push_to_client(req.client_id, turn)
        return {"ok": True, "session_id": session_id, "round": runtime.session.round}

    async def merchant_turn(self, turn: A2A_DialogueTurn) -> dict[str, Any]:
        session_id = str(turn.session_id)
        async with self._lock:
            runtime = self._sessions.get(session_id)
        if runtime is None:
            raise ValueError("session not found")
        if runtime.session.status != DialogueSessionStatus.OPEN:
            raise ValueError("session closed")

        if turn.sender_role != DialogueRole.MERCHANT or turn.sender_id != runtime.session.merchant_id:
            raise ValueError("merchant sender mismatch")

        runtime.session.round = max(runtime.session.round, int(turn.round))
        runtime.session.updated_at = time.time()
        runtime.turns.append(turn)
        await self._push_to_client(runtime.session.client_id, turn)
        return {"ok": True, "session_id": session_id, "round": runtime.session.round}

    async def close_dialogue(self, session_id: UUID) -> dict[str, Any]:
        key = str(session_id)
        async with self._lock:
            runtime = self._sessions.get(key)
        if runtime is None:
            raise ValueError("session not found")
        runtime.session.status = DialogueSessionStatus.CLOSED
        runtime.session.updated_at = time.time()
        return {"ok": True, "session_id": key, "status": runtime.session.status}

    async def get_dialogue(self, session_id: UUID) -> A2A_DialogueSessionView:
        key = str(session_id)
        async with self._lock:
            runtime = self._sessions.get(key)
        if runtime is None:
            raise ValueError("session not found")
        return A2A_DialogueSessionView(session=runtime.session, turns=list(runtime.turns))

    async def _push_to_client(self, client_id: str, turn: A2A_DialogueTurn) -> None:
        async with self._lock:
            ws = self._client_ws.get(client_id)
        if ws is None:
            return
        payload = {"type": "a2a_dialogue_turn", "turn": turn.model_dump(mode="json")}
        try:
            await ws.send_text(json.dumps(payload, ensure_ascii=False))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"push client failed {client_id}: {e}")

    async def _push_to_merchant(self, merchant_id: str, turn: A2A_DialogueTurn) -> None:
        async with self._lock:
            ws = self._merchant_ws.get(merchant_id)
        if ws is None:
            return
        payload = {"type": "a2a_dialogue_turn", "turn": turn.model_dump(mode="json")}
        try:
            await ws.send_text(json.dumps(payload, ensure_ascii=False))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"push merchant failed {merchant_id}: {e}")

    async def _strategy_hint(self, text: str, item_name: str) -> str:
        if self._openmaic is None:
            return "保持礼貌、聚焦价格与履约能力"
        try:
            hint = await asyncio.to_thread(
                self._openmaic.generate_reply,
                user_message=text,
                inventory_info={"item_name": item_name},
                short_memory="",
                long_profile={},
                fallback_api_key="",
            )
            return str(hint)[:180]
        except Exception:
            return "优先满足用户核心诉求，守住底价"
