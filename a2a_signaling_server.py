from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections import defaultdict
from typing import Dict, List

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from cloud_server.match_orchestrator import MatchOrchestrator
from cloud_server.a2a_orchestrator import TradeArena, parse_intent_message, parse_offer_message
from cloud_server.dialogue_arena import DialogueArena
from audit_broadcaster import AuditBroadcaster
from audit_broadcaster import AuditBroadcaster
from shared.claw_protocol import (
    A2A_ClientTurnRequest,
    A2A_DialogueTurn,
    A2A_StartDialogueRequest,
    A2A_TradeDecision,
    A2A_TradeIntent,
)
from config import settings
from secure_comm import build_secure_envelope, verify_and_unpack_envelope, SecureEnvelopeError, NonceReplayProtector
from order_state import OrderStore
from idempotency_store import IdempotencyStore
from auth_guard import verify_internal_token
from agent_profile_store import AgentProfileStore
from agent_preference import PreferenceMatcher
from runtime_config_store import RuntimeConfigStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
logger = logging.getLogger("claw.signaling")

app = FastAPI(title="Project Claw Signaling Server", description="C 端 / B 端握手中央信令服务器", version="13.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


class ClientIntent(BaseModel):
    client_id: str = Field(...)
    location: str = Field(...)
    demand_text: str = Field(...)
    max_price: float = Field(..., gt=0)
    timeout: float = Field(3.0, ge=1, le=30)
    client_profile: dict = Field(default_factory=dict)


class MerchantOffer(BaseModel):
    merchant_id: str = Field(...)
    reply_text: str = Field(...)
    final_price: float = Field(..., gt=0)
    match_score: float = Field(..., ge=0, le=100)
    eta_minutes: int = Field(0)
    offer_tags: list[str] = Field(default_factory=list)
    score_delta: float = Field(0)
    score_reason: str = Field("")


class IntentBroadcast(BaseModel):
    type: str = "intent_broadcast"
    intent_id: str
    client_id: str
    location: str
    demand_text: str
    max_price: float
    timestamp: float = Field(default_factory=time.time)


class SignalingResponse(BaseModel):
    intent_id: str
    client_id: str
    offers: List[MerchantOffer]
    total_merchants: int
    responded: int
    elapsed_ms: float
    timestamp: float = Field(default_factory=time.time)


class ExecuteTradeRequest(BaseModel):
    intent_id: str = Field(..., min_length=1)
    client_id: str = Field(..., min_length=1)
    merchant_id: str = Field(..., min_length=1)
    reply_text: str = Field(..., min_length=1)
    final_price: float = Field(..., ge=0)
    eta_minutes: int = Field(0, ge=0)


class SandboxRequest(BaseModel):
    client_id: str
    merchant_id: str
    item: str
    target: float = Field(..., gt=0)


class ClientProfileUpsert(BaseModel):
    client_id: str
    profile: dict = Field(default_factory=dict)


class MerchantProfileUpsert(BaseModel):
    merchant_id: str
    profile: dict = Field(default_factory=dict)


class MerchantConnection:
    def __init__(self, merchant_id: str, ws: WebSocket):
        self.merchant_id = merchant_id
        self.ws = ws
        self.connected_at = time.time()
        self.last_ping = time.time()
        self.alive = True

    async def send_json(self, data: dict) -> bool:
        try:
            await self.ws.send_text(json.dumps(data, ensure_ascii=False))
            return True
        except Exception as e:
            logger.warning(f"[B:{self.merchant_id}] 发送失败: {e}")
            self.alive = False
            return False

    async def ping(self) -> bool:
        try:
            await self.ws.send_text(json.dumps({"type": "ping", "ts": time.time()}))
            self.last_ping = time.time()
            return True
        except Exception:
            self.alive = False
            return False


class ConnectionManager:
    PING_INTERVAL = 20.0
    PONG_TIMEOUT = 10.0

    def __init__(self):
        self._merchants: Dict[str, MerchantConnection] = {}
        self._lock = asyncio.Lock()
        self._pending: Dict[str, Dict[str, MerchantOffer]] = defaultdict(dict)
        self.signing_secret = settings.A2A_SIGNING_SECRET
        self.encryption_key = settings.A2A_ENCRYPTION_KEY
        self.replay_guard = NonceReplayProtector(ttl_seconds=180)
        self.order_store = OrderStore()
        self.idempotency = IdempotencyStore(redis_url=settings.REDIS_URL, ttl_seconds=settings.IDEMPOTENCY_TTL_SECONDS)
        self.profiles = AgentProfileStore(redis_url=settings.REDIS_URL, ttl_seconds=settings.PROFILE_TTL_SECONDS)
        self.preference_matcher = PreferenceMatcher()
        self.runtime_store = RuntimeConfigStore(redis_url=settings.REDIS_URL)
        self.preference_matcher.apply_runtime(self.runtime_store.load())
        self._intent_meta: dict[str, dict] = {}
        self.metrics = {
            "intent_total": 0,
            "offer_total": 0,
            "offer_adjusted": 0,
            "execute_total": 0,
            "execute_success": 0,
            "execute_fail": 0,
            "strategy_counts": {},
        }

    def _secure_payload(self, payload: dict, sender_id: str, receiver_id: str) -> dict:
        env = build_secure_envelope(
            payload=payload,
            sender_id=sender_id,
            receiver_id=receiver_id,
            secret=self.signing_secret,
            encryption_key=self.encryption_key,
        )
        return {"type": "secure_envelope", "envelope": env}

    def _extract_payload(self, message: dict, expected_receiver_id: str) -> dict:
        if message.get("type") != "secure_envelope":
            return message
        env = message.get("envelope", {})
        sender_id = str(env.get("sender_id", ""))
        nonce = str(env.get("nonce", ""))
        ts = float(env.get("ts", 0))
        self.replay_guard.check_and_mark(sender_id=sender_id, nonce=nonce, ts=ts)
        return verify_and_unpack_envelope(
            envelope=env,
            expected_receiver_id=expected_receiver_id,
            secret=self.signing_secret,
            encryption_key=self.encryption_key,
        )

    async def register_merchant(self, merchant_id: str, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self._merchants[merchant_id] = MerchantConnection(merchant_id, ws)
        logger.info(f"[SignalingServer] B 端注册: {merchant_id} (在线: {len(self._merchants)})")

    async def unregister_merchant(self, merchant_id: str):
        async with self._lock:
            self._merchants.pop(merchant_id, None)
        logger.info(f"[SignalingServer] B 端离线: {merchant_id} (在线: {len(self._merchants)})")

    async def broadcast_intent(self, intent: ClientIntent) -> SignalingResponse:
        intent_id = str(uuid.uuid4())[:8]
        start = time.time()
        msg = IntentBroadcast(intent_id=intent_id, client_id=intent.client_id, location=intent.location, demand_text=intent.demand_text, max_price=intent.max_price).model_dump()
        async with self._lock:
            merchants = list(self._merchants.values())
        total = len(merchants)
        logger.info(f"[{intent_id}] 广播 Intent 给 {total} 个 B 端 client={intent.client_id}")
        self._pending[intent_id] = {}
        self.metrics["intent_total"] += 1
        self.order_store.create_intent(intent_id=intent_id, client_id=intent.client_id, demand_text=intent.demand_text, max_price=float(intent.max_price), location=intent.location)
        self._intent_meta[intent_id] = {
            "client_id": intent.client_id,
            "client_profile": intent.client_profile or self.profiles.get_client(intent.client_id),
            "max_price": float(intent.max_price),
        }
        self.order_store.mark_broadcasted(intent_id, total_merchants=total)
        await asyncio.gather(
            *[
                m.send_json(self._secure_payload(msg, sender_id="signaling", receiver_id=m.merchant_id))
                for m in merchants
            ],
            return_exceptions=True,
        )

        try:
            await asyncio.wait_for(self._wait_all(intent_id, total), timeout=intent.timeout)
        except asyncio.TimeoutError:
            logger.info(f"[{intent_id}] 等待超时 {intent.timeout}s")
        offers_dict = self._pending.pop(intent_id, {})
        offers = sorted([o for o in offers_dict.values() if o.final_price <= intent.max_price], key=lambda o: o.match_score, reverse=True)
        elapsed = (time.time() - start) * 1000
        logger.info(f"[{intent_id}] 汇总完成: responded={len(offers_dict)}/{total} valid_offers={len(offers)} elapsed={elapsed:.0f}ms")
        return SignalingResponse(intent_id=intent_id, client_id=intent.client_id, offers=offers, total_merchants=total, responded=len(offers_dict), elapsed_ms=round(elapsed, 1))

    async def _wait_all(self, intent_id: str, total: int):
        while True:
            if len(self._pending.get(intent_id, {})) >= total:
                return
            await asyncio.sleep(0.05)

    async def receive_offer(self, intent_id: str, offer: MerchantOffer):
        if intent_id in self._pending:
            meta = self._intent_meta.get(intent_id, {})
            client_profile = meta.get("client_profile", {})
            merchant_profile = self.profiles.get_merchant(offer.merchant_id)
            decision = self.preference_matcher.decide(
                base_match_score=float(offer.match_score),
                client_profile={**client_profile, "max_price": meta.get("max_price", 0)},
                merchant_profile=merchant_profile,
                offer=offer.model_dump(),
            )
            adjusted_offer = offer.model_copy(update={
                "match_score": decision.final_score,
                "score_delta": decision.delta,
                "score_reason": ";".join(decision.reasons),
            })
            self._pending[intent_id][offer.merchant_id] = adjusted_offer
            self.metrics["offer_total"] += 1
            if decision.delta != 0:
                self.metrics["offer_adjusted"] += 1
            self.metrics["strategy_counts"][decision.strategy] = self.metrics["strategy_counts"].get(decision.strategy, 0) + 1
            self.order_store.add_offer(intent_id, adjusted_offer.model_dump())
            logger.info(f"[{intent_id}] 收到 Offer from {offer.merchant_id} base={offer.match_score:.1f} adjusted={adjusted_offer.match_score:.1f} delta={decision.delta:+.1f}")

    async def dispatch_execute_trade(self, body: ExecuteTradeRequest) -> dict:
        self.metrics["execute_total"] += 1
        conn = self._merchants.get(body.merchant_id)
        if not conn or not conn.alive:
            self.order_store.mark_failed(body.intent_id, reason="merchant_offline")
            self.metrics["execute_fail"] += 1
            raise HTTPException(status_code=404, detail="目标商家不在线")
        payload = {"type": "execute_trade", "intent_id": body.intent_id, "client_id": body.client_id, "merchant_id": body.merchant_id, "reply_text": body.reply_text, "final_price": body.final_price, "eta_minutes": body.eta_minutes, "ts": time.time()}
        self.order_store.mark_executing(body.intent_id, selected_offer={"merchant_id": body.merchant_id, "reply_text": body.reply_text, "final_price": body.final_price, "eta_minutes": body.eta_minutes})
        secure_payload = self._secure_payload(payload, sender_id="signaling", receiver_id=body.merchant_id)
        try:
            ok = await asyncio.wait_for(conn.send_json(secure_payload), timeout=settings.EXECUTE_TRADE_SEND_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            self.order_store.mark_failed(body.intent_id, reason="execute_trade_timeout")
            self.metrics["execute_fail"] += 1
            raise HTTPException(status_code=504, detail="execute_trade 下发超时")
        if not ok:
            self.order_store.mark_failed(body.intent_id, reason="execute_trade_send_failed")
            self.metrics["execute_fail"] += 1
            raise HTTPException(status_code=502, detail="execute_trade 下发失败")
        logger.info(f"[{body.intent_id}] execute_trade -> {body.merchant_id} price={body.final_price}")
        result = {"ok": True, "merchant_id": body.merchant_id, "intent_id": body.intent_id}
        self.order_store.mark_executed(body.intent_id, result=result)
        self.metrics["execute_success"] += 1
        return result
        

    async def heartbeat_loop(self):
        while True:
            await asyncio.sleep(self.PING_INTERVAL)
            async with self._lock:
                merchants = list(self._merchants.values())
            dead = []
            for conn in merchants:
                ok = await conn.ping()
                if (not ok) or (time.time() - conn.last_ping > self.PING_INTERVAL + self.PONG_TIMEOUT):
                    dead.append(conn.merchant_id)
            for mid in dead:
                await self.unregister_merchant(mid)
                logger.warning(f"[SignalingServer] 心跳超时，移除 B 端: {mid}")

    def stats(self) -> dict:
        return {
            "online_merchants": len(self._merchants),
            "merchant_ids": list(self._merchants.keys()),
            "pending_intents": len(self._pending),
            "metrics": self.metrics,
        }


# ─── 审计事件广播器（驱动上帝视角大屏）───────────────────────────────────────
class AuditBroadcaster:
    """将所有 A2A 事件实时推送给所有监控连接（上帝视角大屏）。"""

    def __init__(self):
        self._clients: list[asyncio.Queue] = []
        self._lock = asyncio.Lock()
        # 累计统计
        self.total_negotiations: int = 0
        self.total_savings: float = 0.0
        self.trade_log: list[dict] = []

    async def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        async with self._lock:
            self._clients.append(q)
        return q

    async def unsubscribe(self, q: asyncio.Queue) -> None:
        async with self._lock:
            try:
                self._clients.remove(q)
            except ValueError:
                pass

    async def emit(self, event: dict) -> None:
        """向所有监控客户端广播事件。"""
        event.setdefault("ts", time.time())
        async with self._lock:
            dead = []
            for q in self._clients:
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    dead.append(q)
            for q in dead:
                try:
                    self._clients.remove(q)
                except ValueError:
                    pass

    def record_trade(self, merchant_id: str, item: str, normal_price: float,
                     final_price: float, tags: list[str]) -> None:
        savings = max(0.0, normal_price - final_price)
        self.total_negotiations += 1
        self.total_savings += savings
        self.trade_log.append({
            "ts": time.time(),
            "merchant_id": merchant_id,
            "item": item,
            "normal_price": normal_price,
            "final_price": final_price,
            "savings": round(savings, 2),
            "tags": tags,
        })
        if len(self.trade_log) > 500:
            self.trade_log = self.trade_log[-500:]

    def snapshot(self) -> dict:
        return {
            "online_merchants": 0,  # 由调用方填充
            "total_negotiations": self.total_negotiations,
            "total_savings": round(self.total_savings, 2),
            "recent_trades": self.trade_log[-20:],
            "audit_subscribers": len(self._clients),
        }


audit = AuditBroadcaster()
audit = AuditBroadcaster()
manager = ConnectionManager()
match_orchestrator = MatchOrchestrator()
trade_arena = TradeArena(timeout_seconds=3.0, top_k=3)
dialogue_arena = DialogueArena()


@app.on_event("startup")
async def startup():
    audit.init_lock()
    asyncio.ensure_future(manager.heartbeat_loop())
    logger.info("=" * 60)
    logger.info("Project Claw Signaling Server v13.0 启动")
    logger.info("B 端注册: ws://<host>:8765/ws/merchant/{merchant_id}")
    logger.info("C 端意图: POST http://<host>:8765/intent")
    logger.info("C 端成交: POST http://<host>:8765/execute_trade")
    logger.info("C 端 WS:  ws://<host>:8765/ws/client/{client_id}")
    logger.info("=" * 60)


@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": time.time(), **manager.stats()}


@app.get("/stats")
async def stats():
    return manager.stats()


@app.get("/runtime/preference")
async def runtime_preference(_auth: None = Depends(verify_internal_token)):
    return manager.preference_matcher.get_runtime()


@app.post("/runtime/preference/weights/{strategy}")
async def update_preference_weights(strategy: str, payload: dict, _auth: None = Depends(verify_internal_token)):
    updated = manager.preference_matcher.update_strategy_weights(strategy=strategy, patch=payload)
    manager.runtime_store.save(manager.preference_matcher.get_runtime())
    return {"strategy": strategy, "weights": updated}


@app.post("/runtime/preference/rollout")
async def update_preference_rollout(payload: dict, _auth: None = Depends(verify_internal_token)):
    rollout = manager.preference_matcher.update_ab_rollout(payload)
    manager.runtime_store.save(manager.preference_matcher.get_runtime())
    return {"ab_rollout": rollout}


@app.get("/metrics")
async def export_metrics():
    m = manager.metrics
    lines = [
        "# HELP claw_intent_total total intent count",
        "# TYPE claw_intent_total counter",
        f"claw_intent_total {m.get('intent_total', 0)}",
        "# HELP claw_offer_total total offers received",
        "# TYPE claw_offer_total counter",
        f"claw_offer_total {m.get('offer_total', 0)}",
        "# HELP claw_offer_adjusted personalized adjusted offers",
        "# TYPE claw_offer_adjusted counter",
        f"claw_offer_adjusted {m.get('offer_adjusted', 0)}",
        "# HELP claw_execute_total total execute requests",
        "# TYPE claw_execute_total counter",
        f"claw_execute_total {m.get('execute_total', 0)}",
        "# HELP claw_execute_success successful execute",
        "# TYPE claw_execute_success counter",
        f"claw_execute_success {m.get('execute_success', 0)}",
        "# HELP claw_execute_fail failed execute",
        "# TYPE claw_execute_fail counter",
        f"claw_execute_fail {m.get('execute_fail', 0)}",
    ]
    for strategy, cnt in (m.get("strategy_counts", {}) or {}).items():
        lines.append(f"claw_strategy_offer_total{{strategy=\"{strategy}\"}} {cnt}")
    return StreamingResponse(iter(["\n".join(lines) + "\n"]), media_type="text/plain; version=0.0.4")


@app.get("/orders")
async def orders(limit: int = 50):
    limit = max(1, min(limit, 200))
    return {"items": manager.order_store.list_recent(limit=limit)}


@app.get("/orders/{intent_id}")
async def order_detail(intent_id: str):
    data = manager.order_store.get(intent_id)
    if not data:
        raise HTTPException(status_code=404, detail="intent_id not found")
    return data


@app.post("/profiles/client")
async def upsert_client_profile(body: ClientProfileUpsert, _auth: None = Depends(verify_internal_token)):
    return manager.profiles.upsert_client(body.client_id, body.profile)


@app.post("/profiles/merchant")
async def upsert_merchant_profile(body: MerchantProfileUpsert, _auth: None = Depends(verify_internal_token)):
    return manager.profiles.upsert_merchant(body.merchant_id, body.profile)


@app.get("/profiles/client/{client_id}")
async def get_client_profile(client_id: str, _auth: None = Depends(verify_internal_token)):
    return {"client_id": client_id, "profile": manager.profiles.get_client(client_id)}


@app.get("/profiles/merchant/{merchant_id}")
async def get_merchant_profile(merchant_id: str, _auth: None = Depends(verify_internal_token)):
    return {"merchant_id": merchant_id, "profile": manager.profiles.get_merchant(merchant_id)}


@app.post("/match/explain")
async def explain_match(offer: MerchantOffer, client_profile: dict | None = None, merchant_profile: dict | None = None):
    c = client_profile or {}
    m = merchant_profile or {}
    decision = manager.preference_matcher.decide(
        base_match_score=float(offer.match_score),
        client_profile=c,
        merchant_profile=m,
        offer=offer.model_dump(),
    )
    return {"final_score": decision.final_score, "delta": decision.delta, "reasons": decision.reasons, "strategy": decision.strategy}


@app.get("/socialstream/{client_id}")
async def social_stream(client_id: str):
    return StreamingResponse(match_orchestrator.stream_events(client_id), media_type="text/event-stream")


@app.get("/a2a/stream/{client_id}")
async def a2a_stream(client_id: str):
    return StreamingResponse(trade_arena.stream_client_events(client_id), media_type="text/event-stream")


@app.post("/a2a/intent")
async def a2a_intent(intent: A2A_TradeIntent, _auth: None = Depends(verify_internal_token), idempotency_key: str = Header(default="")):
    key = idempotency_key or f"a2a_intent:{intent.client_id}:{intent.item_name}:{intent.expected_price}:{intent.max_distance_km}"
    cached = manager.idempotency.get(key)
    if cached is not None:
        return cached
    result = await trade_arena.submit_intent(intent)
    manager.idempotency.set(key, result)
    return result


@app.post("/a2a/decision")
async def a2a_decision(decision: A2A_TradeDecision, final_price: float = 0.0, _auth: None = Depends(verify_internal_token)):
    return await trade_arena.dispatch_trade_decision(decision=decision, final_price=final_price)





@app.post("/a2a/dialogue/profile/client")
async def a2a_dialogue_profile_client(payload: dict, _auth: None = Depends(verify_internal_token)):
    return await dialogue_arena.upsert_client_profile(payload)


@app.post("/a2a/dialogue/profile/merchant")
async def a2a_dialogue_profile_merchant(payload: dict, _auth: None = Depends(verify_internal_token)):
    return await dialogue_arena.upsert_merchant_profile(payload)


@app.post("/a2a/dialogue/start")
async def a2a_dialogue_start(req: A2A_StartDialogueRequest, _auth: None = Depends(verify_internal_token)):
    return await dialogue_arena.start_dialogue(req)


@app.post("/a2a/dialogue/client_turn")
async def a2a_dialogue_client_turn(req: A2A_ClientTurnRequest, _auth: None = Depends(verify_internal_token)):
    return await dialogue_arena.client_turn(req)


@app.get("/a2a/dialogue/{session_id}")
async def a2a_dialogue_get(session_id: str, _auth: None = Depends(verify_internal_token)):
    from uuid import UUID

    return (await dialogue_arena.get_dialogue(UUID(session_id))).model_dump(mode="json")


@app.post("/a2a/dialogue/{session_id}/close")
async def a2a_dialogue_close(session_id: str, _auth: None = Depends(verify_internal_token)):
    from uuid import UUID

    return await dialogue_arena.close_dialogue(UUID(session_id))


@app.post("/sandbox/match")
async def sandbox_match(body: SandboxRequest):
    result = await match_orchestrator.run_sandbox(client_id=body.client_id, merchant_id=body.merchant_id, buyer_payload={"item": body.item, "target": body.target})
    return JSONResponse(result)


@app.post("/intent", response_model=SignalingResponse)
async def post_intent(intent: ClientIntent, _auth: None = Depends(verify_internal_token), idempotency_key: str = Header(default="")):
    if not manager._merchants:
        raise HTTPException(status_code=503, detail="暂无在线商家，请稍后再试")
    if intent.client_profile:
        manager.profiles.upsert_client(intent.client_id, intent.client_profile)
    key = idempotency_key or f"intent:{intent.client_id}:{intent.location}:{intent.demand_text}:{intent.max_price}"
    cached = manager.idempotency.get(key)
    if cached is not None:
        return SignalingResponse(**cached)
    result = await manager.broadcast_intent(intent)
    # 审计广播
    import asyncio as _aio
    _aio.ensure_future(audit.emit({"type":"intent","role":"info","text":f"[{result.intent_id}] C端广播: {intent.demand_text} max=¥{intent.max_price} merchants={result.total_merchants}"}))
    if result.offers:
        for _o in result.offers[:3]:
            _aio.ensure_future(audit.emit({"type":"agent","role":"seller","text":f"[B端Agent:{_o.merchant_id}] 报价 ¥{_o.final_price} score={_o.match_score:.1f}"}))
        best = result.offers[0]
        _aio.ensure_future(audit.emit({"type":"deal","role":"deal","text":f"[成交] {best.merchant_id} ¥{best.final_price} 节省¥{round(intent.max_price-best.final_price,2)}"}))
        audit.record_trade(best.merchant_id, intent.demand_text, intent.max_price, best.final_price, best.offer_tags)
    manager.idempotency.set(key, result.model_dump())
    return result


@app.post("/execute_trade")
async def execute_trade(body: ExecuteTradeRequest, _auth: None = Depends(verify_internal_token), idempotency_key: str = Header(default="")):
    key = idempotency_key or f"execute:{body.intent_id}:{body.client_id}:{body.merchant_id}:{body.final_price}"
    cached = manager.idempotency.get(key)
    if cached is not None:
        return cached
    result = await manager.dispatch_execute_trade(body)
    manager.idempotency.set(key, result)
    return result


@app.websocket("/ws/merchant/{merchant_id}")
async def merchant_ws(websocket: WebSocket, merchant_id: str):
    await manager.register_merchant(merchant_id, websocket)
    try:
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
                data = json.loads(raw)
                msg_type = data.get("type", "")
                try:
                    data = manager._extract_payload(data, expected_receiver_id="signaling")
                    msg_type = data.get("type", "")
                except SecureEnvelopeError as e:
                    logger.warning(f"[Signaling] 非法安全消息: {e}")
                    continue
                if msg_type == "pong":
                    conn = manager._merchants.get(merchant_id)
                    if conn:
                        conn.last_ping = time.time()
                elif msg_type == "offer":
                    intent_id = data.get("intent_id", "")
                    try:
                        offer = MerchantOffer(merchant_id=merchant_id, reply_text=data.get("reply_text", ""), final_price=float(data.get("final_price", 0)), match_score=float(data.get("match_score", 0)), eta_minutes=int(data.get("eta_minutes", 0)), offer_tags=list(data.get("offer_tags", []) or []))
                        await manager.receive_offer(intent_id, offer)
                    except Exception as e:
                        logger.error(f"[B:{merchant_id}] Offer 解析失败: {e}")
                elif msg_type == "register":
                    logger.info(f"[B:{merchant_id}] 注册信息: {data}")
                    manager.profiles.upsert_merchant(merchant_id, {"tags": list(data.get("merchant_tags", []) or [])})
                    await websocket.send_text(json.dumps(manager._secure_payload({"type": "registered", "node_id": merchant_id, "ts": time.time()}, sender_id="signaling", receiver_id=merchant_id), ensure_ascii=False))
                else:
                    logger.debug(f"[B:{merchant_id}] 未知消息: {msg_type}")
            except asyncio.TimeoutError:
                conn = manager._merchants.get(merchant_id)
                if conn:
                    await conn.ping()
    except WebSocketDisconnect:
        logger.info(f"[B:{merchant_id}] 主动断开")
    except Exception as e:
        logger.error(f"[B:{merchant_id}] 连接异常: {e}")
    finally:
        await manager.unregister_merchant(merchant_id)


@app.websocket("/ws/client/{client_id}")
async def client_ws(websocket: WebSocket, client_id: str):
    await websocket.accept()
    logger.info(f"[C:{client_id}] 连接建立")
    try:
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=90.0)
                data = json.loads(raw)
                msg_type = data.get("type", "")
                try:
                    data = manager._extract_payload(data, expected_receiver_id="signaling")
                    msg_type = data.get("type", "")
                except SecureEnvelopeError as e:
                    logger.warning(f"[Signaling] 非法安全消息: {e}")
                    continue
                if msg_type == "pong":
                    pass
                elif msg_type == "intent":
                    try:
                        intent = ClientIntent(client_id=client_id, location=data.get("location", ""), demand_text=data.get("demand_text", ""), max_price=float(data.get("max_price", 999)), timeout=float(data.get("timeout", 3.0)), client_profile=dict(data.get("client_profile", {}) or {}))
                        result = await manager.broadcast_intent(intent)
                        await websocket.send_text(json.dumps({"type": "offers", "intent_id": result.intent_id, "offers": [o.model_dump() for o in result.offers], "total_merchants": result.total_merchants, "responded": result.responded, "elapsed_ms": result.elapsed_ms, "ts": time.time()}, ensure_ascii=False))
                    except Exception as e:
                        logger.error(f"[C:{client_id}] 处理 Intent 失败: {e}")
                        await websocket.send_text(json.dumps({"type": "error", "error": str(e)}))
                else:
                    logger.debug(f"[C:{client_id}] 未知消息: {msg_type}")
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({"type": "ping", "ts": time.time()}))
    except WebSocketDisconnect:
        logger.info(f"[C:{client_id}] 断开")
    except Exception as e:
        logger.error(f"[C:{client_id}] 异常: {e}")


@app.websocket("/ws/a2a/merchant/{merchant_id}")
async def a2a_merchant_ws(websocket: WebSocket, merchant_id: str, distance_km: float = 0.0, token: str = ""):
    # Token 校验（INTERNAL_API_TOKEN 未配置时开放）
    _expected = settings.INTERNAL_API_TOKEN
    if _expected and token != _expected:
        await websocket.accept()
        await websocket.send_text(json.dumps({"type":"error","error":"unauthorized"}))
        await websocket.close(code=4001)
        return
    await trade_arena.register_merchant(merchant_id=merchant_id, ws=websocket, distance_km=distance_km)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                offer = parse_offer_message(raw)
                await trade_arena.on_merchant_offer(offer)
            except Exception as e:
                logger.warning(f"[A2A Merchant:{merchant_id}] offer parse/process failed: {e}")
    except WebSocketDisconnect:
        logger.info(f"[A2A Merchant:{merchant_id}] disconnected")
    except Exception as e:
        logger.error(f"[A2A Merchant:{merchant_id}] ws error: {e}")
    finally:
        await trade_arena.unregister_merchant(merchant_id)


@app.websocket("/ws/a2a/client/{client_id}")
async def a2a_client_ws(websocket: WebSocket, client_id: str):
    await trade_arena.register_client_ws(client_id=client_id, ws=websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                intent = parse_intent_message(raw)
                if intent.client_id != client_id:
                    await websocket.send_text(json.dumps({"type": "error", "error": "client_id mismatch"}, ensure_ascii=False))
                    continue
                await trade_arena.submit_intent(intent)
            except Exception as e:
                logger.warning(f"[A2A Client:{client_id}] intent parse/process failed: {e}")
                await websocket.send_text(json.dumps({"type": "error", "error": str(e)}, ensure_ascii=False))
    except WebSocketDisconnect:
        logger.info(f"[A2A Client:{client_id}] disconnected")
    except Exception as e:
        logger.error(f"[A2A Client:{client_id}] ws error: {e}")
    finally:
        await trade_arena.unregister_client_ws(client_id)




@app.websocket("/ws/a2a/dialogue/merchant/{merchant_id}")
async def a2a_dialogue_merchant_ws(websocket: WebSocket, merchant_id: str, token: str = ""):
    await websocket.accept()
    await dialogue_arena.register_merchant_ws(merchant_id=merchant_id, ws=websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
                if data.get("type") != "a2a_dialogue_turn":
                    await websocket.send_text(json.dumps({"type": "error", "error": "unsupported type"}, ensure_ascii=False))
                    continue
                turn = A2A_DialogueTurn.model_validate(data.get("turn", {}))
                await dialogue_arena.merchant_turn(turn)
            except Exception as e:
                logger.warning(f"[A2A Dialogue Merchant:{merchant_id}] parse/process failed: {e}")
    except WebSocketDisconnect:
        logger.info(f"[A2A Dialogue Merchant:{merchant_id}] disconnected")
    finally:
        await dialogue_arena.unregister_merchant_ws(merchant_id)


@app.websocket("/ws/a2a/dialogue/client/{client_id}")
async def a2a_dialogue_client_ws(websocket: WebSocket, client_id: str):
    await websocket.accept()
    await dialogue_arena.register_client_ws(client_id=client_id, ws=websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
                if data.get("type") != "a2a_dialogue_client_turn":
                    await websocket.send_text(json.dumps({"type": "error", "error": "unsupported type"}, ensure_ascii=False))
                    continue
                req = A2A_ClientTurnRequest.model_validate(data.get("payload", {}))
                if req.client_id != client_id:
                    await websocket.send_text(json.dumps({"type": "error", "error": "client_id mismatch"}, ensure_ascii=False))
                    continue
                await dialogue_arena.client_turn(req)
            except Exception as e:
                logger.warning(f"[A2A Dialogue Client:{client_id}] parse/process failed: {e}")
                await websocket.send_text(json.dumps({"type": "error", "error": str(e)}, ensure_ascii=False))
    except WebSocketDisconnect:
        logger.info(f"[A2A Dialogue Client:{client_id}] disconnected")
    finally:
        await dialogue_arena.unregister_client_ws(client_id)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("a2a_signaling_server:app", host=settings.SIGNALING_HOST, port=settings.SIGNALING_PORT, log_level="info", ws_ping_interval=20, ws_ping_timeout=10)


@app.websocket("/ws/audit_stream")
async def audit_stream_ws(websocket: WebSocket):
    """上帝视角监控大屏实时审计流"""
    await websocket.accept()
    q = await audit.subscribe()
    # 先发送当前快照
    snap = audit.snapshot(online_merchants=len(manager._merchants))
    await websocket.send_text(json.dumps({"type": "snapshot", **snap}, ensure_ascii=False))
    try:
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=20.0)
                await websocket.send_text(json.dumps(event, ensure_ascii=False))
            except asyncio.TimeoutError:
                # 心跳
                await websocket.send_text(json.dumps({"type": "ping", "ts": time.time()}))
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"[audit_stream] error: {e}")
    finally:
        await audit.unsubscribe(q)


@app.get("/audit/snapshot")
async def audit_snapshot_http():
    """HTTP 拉取当前审计快照（Streamlit 初始化用）"""
    snap = audit.snapshot(online_merchants=len(manager._merchants))
    stats = manager.stats()
    return {**snap, **stats}
