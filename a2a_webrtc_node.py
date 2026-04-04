from __future__ import annotations

import asyncio
import contextlib
import json
import os
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from shared.claw_protocol import A2A_MerchantOffer, ExecuteTrade, TradeRequest, sign_payload


# =====================
# Cloud Signaling Router
# =====================


class SignalMessage(BaseModel):
    from_id: str
    to_id: str
    kind: str = Field(..., description="offer|answer|ice")
    payload: dict[str, Any] = Field(default_factory=dict)
    ts: float = Field(default_factory=time.time)


class ExecuteTradeSettleBody(BaseModel):
    merchant_id: str
    execute_trade: ExecuteTrade
    signature: str


@dataclass
class _SignalStore:
    queues: dict[str, list[SignalMessage]]
    lock: asyncio.Lock


_SIGNAL_STORE = _SignalStore(queues=defaultdict(list), lock=asyncio.Lock())


def _verify_bearer_optional(authorization: str = Header(default="")) -> str:
    if not authorization:
        return ""
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing_bearer_token")
    return authorization[7:]


def create_webrtc_signaling_router(
    ledger_manager_getter: Optional[Callable[[], Any]] = None,
) -> APIRouter:
    router = APIRouter(tags=["a2a-webrtc"])

    @router.post("/api/v1/webrtc/signal/send")
    async def webrtc_signal_send(body: SignalMessage, token: str = Depends(_verify_bearer_optional)):
        _ = token  # 复用现有鉴权体系时可在外层启用 strict 校验
        async with _SIGNAL_STORE.lock:
            _SIGNAL_STORE.queues[body.to_id].append(body)
        return {"ok": True, "to_id": body.to_id, "kind": body.kind}

    @router.get("/api/v1/webrtc/signal/poll/{peer_id}")
    async def webrtc_signal_poll(peer_id: str, timeout_sec: float = 15.0, token: str = Depends(_verify_bearer_optional)):
        _ = token
        deadline = time.time() + max(0.2, min(timeout_sec, 25.0))
        while time.time() < deadline:
            async with _SIGNAL_STORE.lock:
                q = _SIGNAL_STORE.queues.get(peer_id, [])
                if q:
                    items = [m.model_dump() for m in q[:50]]
                    _SIGNAL_STORE.queues[peer_id] = q[50:]
                    return {"ok": True, "items": items}
            await asyncio.sleep(0.05)
        return {"ok": True, "items": []}

    @router.post("/api/v1/webrtc/execute/settle")
    async def webrtc_execute_settle(body: ExecuteTradeSettleBody, token: str = Depends(_verify_bearer_optional)):
        _ = token
        signing_secret = os.getenv("A2A_SIGNING_SECRET", os.getenv("A2A_SIGN_KEY", "claw-a2a-signing-secret"))
        expected_sig = sign_payload(body.execute_trade, signing_secret)
        if expected_sig != body.signature:
            raise HTTPException(403, "bad_execute_trade_signature")

        result = {
            "ok": True,
            "request_id": str(body.execute_trade.request_id),
            "merchant_id": body.merchant_id,
            "final_price": body.execute_trade.final_price,
            "fee_ratio": 0.01,
        }

        ledger_manager = ledger_manager_getter() if ledger_manager_getter else None
        if ledger_manager:
            fee_amount = round(float(body.execute_trade.final_price) * 0.01, 6)
            status, txn = await ledger_manager.deduct_routing_token(
                merchant_id=body.merchant_id,
                amount=fee_amount,
                trade_id=body.execute_trade.trade_id,
            )
            result["billing"] = {
                "deducted": fee_amount,
                "balance": status.balance,
                "currency_unit": status.currency_unit,
                "transaction": txn.model_dump(),
            }

        return result

    return router


# =====================
# Edge A2A WebRTC Node
# =====================


class A2AWebRTCNode:
    """买手/商户 Agent 之间的 WebRTC DataChannel 节点。"""

    def __init__(
        self,
        *,
        node_id: str,
        signaling_base_url: str,
        auth_token: str = "",
        stun_url: str = "stun:stun.l.google.com:19302",
    ):
        self.node_id = node_id
        self.signaling_base_url = signaling_base_url.rstrip("/")
        self.auth_token = auth_token
        self.stun_url = stun_url

        self._pc = None
        self._dc = None
        self._target_id: Optional[str] = None
        self._poll_task: Optional[asyncio.Task] = None
        self._connected = asyncio.Event()
        self._closed = False
        self.on_json_message: Optional[Callable[[dict[str, Any]], Awaitable[None]]] = None

    async def connect(self, target_id: str, initiator: bool, timeout_sec: float = 20.0) -> None:
        from aiortc import RTCPeerConnection, RTCConfiguration, RTCIceServer, RTCSessionDescription
        from aiortc.sdp import candidate_from_sdp, candidate_to_sdp

        self._target_id = target_id
        cfg = RTCConfiguration(iceServers=[RTCIceServer(urls=[self.stun_url])])
        self._pc = RTCPeerConnection(cfg)

        @self._pc.on("icecandidate")
        async def _on_icecandidate(candidate):
            if candidate is None:
                return
            await self._send_signal(
                kind="ice",
                payload={
                    "candidate": candidate_to_sdp(candidate),
                    "sdpMid": candidate.sdpMid,
                    "sdpMLineIndex": candidate.sdpMLineIndex,
                },
            )

        @self._pc.on("datachannel")
        def _on_datachannel(channel):
            self._bind_datachannel(channel)

        if initiator:
            dc = self._pc.createDataChannel("a2a-negotiation", ordered=True)
            self._bind_datachannel(dc)
            offer = await self._pc.createOffer()
            await self._pc.setLocalDescription(offer)
            await self._send_signal(
                kind="offer",
                payload={
                    "sdp": self._pc.localDescription.sdp,
                    "type": self._pc.localDescription.type,
                },
            )

        self._poll_task = asyncio.create_task(self._poll_signaling_loop(candidate_from_sdp))
        await asyncio.wait_for(self._connected.wait(), timeout=timeout_sec)

    def _bind_datachannel(self, channel):
        self._dc = channel

        @channel.on("open")
        def _on_open():
            self._connected.set()

        @channel.on("message")
        def _on_message(message):
            try:
                data = json.loads(message if isinstance(message, str) else message.decode("utf-8"))
            except Exception:
                return
            if self.on_json_message:
                asyncio.create_task(self.on_json_message(data))

    async def _poll_signaling_loop(self, candidate_from_sdp):
        from aiortc import RTCSessionDescription

        while not self._closed:
            try:
                data = await self._poll_signals(timeout_sec=12.0)
                items = data.get("items", [])
                for item in items:
                    kind = item.get("kind")
                    payload = item.get("payload") or {}

                    if kind == "offer" and self._pc:
                        offer = RTCSessionDescription(sdp=payload["sdp"], type=payload["type"])
                        await self._pc.setRemoteDescription(offer)
                        answer = await self._pc.createAnswer()
                        await self._pc.setLocalDescription(answer)
                        await self._send_signal(
                            kind="answer",
                            payload={
                                "sdp": self._pc.localDescription.sdp,
                                "type": self._pc.localDescription.type,
                            },
                        )

                    elif kind == "answer" and self._pc:
                        answer = RTCSessionDescription(sdp=payload["sdp"], type=payload["type"])
                        await self._pc.setRemoteDescription(answer)

                    elif kind == "ice" and self._pc:
                        c = candidate_from_sdp(payload["candidate"])
                        c.sdpMid = payload.get("sdpMid")
                        c.sdpMLineIndex = payload.get("sdpMLineIndex")
                        await self._pc.addIceCandidate(c)
            except Exception:
                await asyncio.sleep(0.2)

    async def send_trade_request(self, req: TradeRequest) -> None:
        await self.send_json({"msg_type": "TradeRequest", "payload": req.model_dump(mode="json")})

    async def send_merchant_offer(self, offer: A2A_MerchantOffer) -> None:
        await self.send_json({"msg_type": "MerchantOffer", "payload": offer.model_dump(mode="json")})

    async def send_json(self, data: dict[str, Any]) -> None:
        await self._connected.wait()
        if not self._dc:
            raise RuntimeError("datachannel_not_ready")
        self._dc.send(json.dumps(data, ensure_ascii=False))

    async def submit_execute_trade_result(
        self,
        *,
        execute_trade: ExecuteTrade,
        merchant_id: str,
        signing_secret: str,
    ) -> dict[str, Any]:
        signature = sign_payload(execute_trade, signing_secret)
        body = {
            "merchant_id": merchant_id,
            "execute_trade": execute_trade.model_dump(mode="json"),
            "signature": signature,
        }
        return await self._post("/api/v1/webrtc/execute/settle", body)

    async def close(self) -> None:
        self._closed = True
        if self._poll_task:
            self._poll_task.cancel()
            with contextlib.suppress(Exception):
                await self._poll_task
        if self._pc:
            await self._pc.close()

    async def _send_signal(self, *, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._target_id:
            raise RuntimeError("target_id_not_set")
        body = {
            "from_id": self.node_id,
            "to_id": self._target_id,
            "kind": kind,
            "payload": payload,
        }
        return await self._post("/api/v1/webrtc/signal/send", body)

    async def _poll_signals(self, timeout_sec: float = 12.0) -> dict[str, Any]:
        url = f"{self.signaling_base_url}/api/v1/webrtc/signal/poll/{self.node_id}"
        headers = {"Authorization": f"Bearer {self.auth_token}"} if self.auth_token else {}
        async with httpx.AsyncClient(timeout=timeout_sec + 5) as client:
            resp = await client.get(url, params={"timeout_sec": timeout_sec}, headers=headers)
            resp.raise_for_status()
            return resp.json()

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.signaling_base_url}{path}"
        headers = {"Authorization": f"Bearer {self.auth_token}"} if self.auth_token else {}
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(url, json=body, headers=headers)
            resp.raise_for_status()
            return resp.json()
