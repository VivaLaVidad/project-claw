from __future__ import annotations
import asyncio, base64, hashlib, hmac, json, logging, os, sqlite3, sys, time
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Tuple
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request, Header, Depends, BackgroundTasks
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from contextlib import asynccontextmanager

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from shared.claw_protocol import BillingStatus, ExecuteTrade, MatchFoundEvent, MerchantOffer, MsgType, OfferBundle, SignalEnvelope, SocialIntent, TradeRequest, TradeStatus
from shared.a2a_handshake import build_packet, open_packet
try:
    from cloud_server.clearing_service import ClearingService
except Exception:
    class ClearingService:  # fallback to keep hub bootable when clearing module absent
        async def init_models(self):
            return None
from cloud_server.ledger_service import LedgerManager
from cloud_server.social_coordinator import SocialCoordinator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
logger = logging.getLogger("claw.hub")

HARD_TIMEOUT    = float(os.getenv("HUB_REQUEST_HARD_TIMEOUT_SEC", "60"))
SNAPSHOT_TTL   = float(os.getenv("HUB_SNAPSHOT_TTL_SEC", "600"))
EARLY_RETURN_SEC = float(os.getenv("HUB_EARLY_RETURN_SEC", "4"))
SOCIAL_ENABLED = os.getenv("SOCIAL_ENABLED", "0") == "1"
SOCIAL_SIM_THRESHOLD = float(os.getenv("HUB_SOCIAL_SIM_THRESHOLD", "0.85"))
SOCIAL_MAX_DISTANCE_M = float(os.getenv("HUB_SOCIAL_MAX_DISTANCE_M", "5000"))
SOCIAL_MATCH_COOLDOWN_SEC = float(os.getenv("HUB_SOCIAL_MATCH_COOLDOWN_SEC", "600"))
AUDIT_LOG      = os.getenv("HUB_AUDIT_LOG", "hub_audit.log")
DB_PATH        = os.getenv("HUB_DB_PATH", "claw_orders.db")
RATE_LIMIT     = int(os.getenv("HUB_RATE_LIMIT_PER_MIN", "30"))
JWT_SECRET     = os.getenv("HUB_JWT_SECRET", "claw-change-in-prod")
JWT_EXPIRE_SEC = int(os.getenv("HUB_JWT_EXPIRE_SEC", "86400"))
MERCHANT_KEY   = os.getenv("HUB_MERCHANT_KEY", "merchant-shared-key")
# Railway / Zeabur inject PORT dynamically
PORT           = int(os.getenv("PORT", "8765"))
CLEARING_ENABLED = os.getenv("CLEARING_ENABLED", "0") == "1"
LEDGER_ENABLED = os.getenv("LEDGER_ENABLED", "0") == "1"


# ── Audit ────────────────────────────────────────────────────────────────────
def audit(event: str, **fields):
    row = {"ts": time.time(), "event": event, **fields}
    line = json.dumps(row, ensure_ascii=False)
    logger.info(f"[AUDIT] {line}")
    try:
        with open(AUDIT_LOG, "a", encoding="utf-8") as f: f.write(line + "\n")
    except Exception: pass


# ── JWT ──────────────────────────────────────────────────────────────────────
def _b64u(d: bytes) -> str:
    return base64.urlsafe_b64encode(d).rstrip(b"=").decode()
def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))

def jwt_issue(sub: str, role: str) -> str:
    now = int(time.time())
    h = _b64u(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    p = _b64u(json.dumps({"sub": sub, "role": role, "iat": now, "exp": now + JWT_EXPIRE_SEC}).encode())
    s = _b64u(hmac.new(JWT_SECRET.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest())
    return f"{h}.{p}.{s}"

def jwt_verify(token: str) -> dict:
    try:
        parts = token.strip().split(".")
        if len(parts) != 3: raise ValueError("malformed")
        h, p, s = parts
        exp = _b64u(hmac.new(JWT_SECRET.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(s, exp): raise ValueError("bad_sig")
        c = json.loads(_b64d(p))
        if c.get("exp", 0) < time.time(): raise ValueError("token_expired")
        return c
    except HTTPException: raise
    except Exception as e: raise HTTPException(401, f"invalid_token:{e}")

def bearer_claims(authorization: str = Header(default="")) -> dict:
    if not authorization.startswith("Bearer "): raise HTTPException(401, "missing_bearer_token")
    return jwt_verify(authorization[7:])

def ws_verify(token: str, role: str, sub: str) -> dict:
    if not token: raise HTTPException(401, "missing_ws_token")
    c = jwt_verify(token)
    if c.get("role") != role: raise HTTPException(403, f"ws_role_required:{role}")
    if c.get("sub") != sub: raise HTTPException(403, "ws_sub_mismatch")
    return c

# -- Rate Limiter -------------------------------------------------------
class RateLimiter:
    def __init__(self, limit: int, window: float = 60.0):
        self._limit = limit; self._window = window
        self._hits: Dict[str, List[float]] = {}; self._lock = asyncio.Lock()
    async def check(self, key: str) -> bool:
        async with self._lock:
            now = time.time()
            arr = [t for t in self._hits.get(key, []) if now - t < self._window]
            if len(arr) >= self._limit: self._hits[key] = arr; return False
            arr.append(now); self._hits[key] = arr; return True

async def rate_guard(request: Request, claims: dict = Depends(bearer_claims)):
    key = claims.get("sub", request.client.host if request.client else "anon")
    if not await rate_limiter.check(key):
        audit("rate_limit", sub=key); raise HTTPException(429, "rate_limit_exceeded")


# -- OrderDB -----------------------------------------------------------
class OrderDB:
    _DDL = """CREATE TABLE IF NOT EXISTS orders(
        request_id TEXT PRIMARY KEY, client_id TEXT NOT NULL,
        item_name TEXT, demand_text TEXT, max_price REAL, quantity INTEGER, timeout_sec REAL,
        status TEXT DEFAULT 'pending', merchant_id TEXT, final_price REAL, offer_id TEXT,
        created_at REAL, executed_at REAL, error_reason TEXT)"""
    def __init__(self, path: str):
        self._path = path
        with self._conn() as c: c.execute(self._DDL); c.commit()
    def _conn(self):
        c = sqlite3.connect(self._path, check_same_thread=False); c.row_factory = sqlite3.Row; return c
    def upsert_request(self, req: TradeRequest):
        with self._conn() as c:
            c.execute("INSERT OR IGNORE INTO orders(request_id,client_id,item_name,demand_text,max_price,quantity,timeout_sec,status,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (req.request_id,req.client_id,req.item_name,req.demand_text,req.max_price,req.quantity,req.timeout_sec,"pending",time.time())); c.commit()
    def set_executed(self, rid, mid, oid, price):
        with self._conn() as c:
            c.execute("UPDATE orders SET status='executed',merchant_id=?,offer_id=?,final_price=?,executed_at=? WHERE request_id=?",(mid,oid,price,time.time(),rid)); c.commit()
    def set_failed(self, rid, reason):
        with self._conn() as c:
            c.execute("UPDATE orders SET status='failed',error_reason=? WHERE request_id=?",(reason,rid)); c.commit()
    def by_client(self, cid, limit=20):
        with self._conn() as c:
            rows = c.execute("SELECT * FROM orders WHERE client_id=? ORDER BY created_at DESC LIMIT ?",(cid,limit)).fetchall()
        return [dict(r) for r in rows]


# -- MerchantPool ------------------------------------------------------
class MerchantPool:
    ping_interval = 20.0; pong_timeout = 10.0
    def __init__(self): self._conns: Dict[str,WebSocket]={}; self._last_pong: Dict[str,float]={}; self._lock=asyncio.Lock()
    async def register(self, mid, ws):
        await ws.accept()
        async with self._lock: self._conns[mid]=ws; self._last_pong[mid]=time.time()
        audit("merchant_online", merchant_id=mid)
    async def unregister(self, mid):
        existed = mid in self._conns
        async with self._lock: self._conns.pop(mid,None); self._last_pong.pop(mid,None)
        if existed: audit("merchant_offline", merchant_id=mid)
    def count(self): return len(self._conns)
    def ids(self): return list(self._conns.keys())
    def update_pong(self, mid): self._last_pong[mid]=time.time()
    async def broadcast(self, env):
        async with self._lock: targets=list(self._conns.items())
        raw,sent=env.model_dump_json(),[]
        for mid,ws in targets:
            try: await ws.send_text(raw); sent.append(mid)
            except: await self.unregister(mid)
        return sent
    async def send_to(self, mid, env):
        ws=self._conns.get(mid)
        if not ws: return False
        try: await ws.send_text(env.model_dump_json()); return True
        except: await self.unregister(mid); return False
    async def heartbeat_loop(self):
        while True:
            await asyncio.sleep(self.ping_interval)
            async with self._lock: mids=list(self._conns.keys())
            dead=[]
            for mid in mids:
                ws=self._conns.get(mid)
                if not ws: continue
                try:
                    ping=SignalEnvelope(msg_type=MsgType.HEARTBEAT,sender_id="hub",payload={"type":"ping","ts":time.time()})
                    await ws.send_text(ping.model_dump_json())
                except: dead.append(mid)
                if time.time()-self._last_pong.get(mid,0)>self.ping_interval+self.pong_timeout: dead.append(mid)
            for mid in set(dead): await self.unregister(mid)


# -- ClientPool --------------------------------------------------------
class ClientPool:
    def __init__(self): self._conns: Dict[str,WebSocket]={}; self._lock=asyncio.Lock()
    async def register(self, cid, ws):
        await ws.accept()
        async with self._lock: self._conns[cid]=ws
    async def unregister(self, cid):
        async with self._lock: self._conns.pop(cid,None)
    async def send_to(self, cid, env):
        ws=self._conns.get(cid)
        if not ws: return False
        try: await ws.send_text(env.model_dump_json()); return True
        except: await self.unregister(cid); return False
    async def push_status(self, cid, rid, status, extra=None):
        p={"request_id":rid,"status":status,"ts":time.time()}
        if extra: p.update(extra)
        await self.send_to(cid,SignalEnvelope(msg_type=MsgType.ACK,sender_id="hub",payload=p))

# ── Geo helper ──────────────────────────────────────────────────────────────
import math

def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """两点间距离（米）"""
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


_A2A_PENDING: Dict[Tuple[str, str], Dict[str, MerchantOffer]] = defaultdict(dict)
_A2A_RECOMMENDED: Dict[str, dict] = {}


def _recommend_a2a(source_id: str, request_id: str) -> Optional[dict]:
    offers = list(_A2A_PENDING.get((source_id, request_id), {}).values())
    if len(offers) < 3:
        return None

    src = coordinator._merchant_geo.get(source_id) if 'coordinator' in globals() else None

    def _dist(mid: str) -> float:
        dst = coordinator._merchant_geo.get(mid) if 'coordinator' in globals() else None
        if not src or not dst:
            return 1e12
        return _haversine_m(src[0], src[1], dst[0], dst[1])

    ranked = sorted(offers, key=lambda o: (o.final_price, _dist(o.merchant_id)))
    best = ranked[0]
    return {
        "request_id": request_id,
        "source_id": source_id,
        "offer_count": len(ranked),
        "recommended": {
            **best.model_dump(),
            "distance_m": round(_dist(best.merchant_id), 1),
        },
        "offers": [
            {
                **o.model_dump(),
                "distance_m": round(_dist(o.merchant_id), 1),
            }
            for o in ranked
        ],
    }


async def _handle_a2a_packet_from_merchant(sender_id: str, packet_dict: dict):
    opened = open_packet(packet_dict, expected_target_id="")
    header = opened["header"]
    payload = opened["payload"]
    kind = str(payload.get("kind", "")).strip().lower()

    # 防伪造 source
    if header.get("source_id") != sender_id:
        raise ValueError("a2a_source_mismatch")

    target_id = header.get("target_id", "")

    if kind == "trade_request":
        env = SignalEnvelope(msg_type=MsgType.ACK, sender_id="hub", payload={"type": "a2a_packet", "packet": packet_dict})
        ok = await merchant_pool.send_to(target_id, env)
        if not ok:
            raise ValueError("a2a_target_offline")
        return

    if kind == "merchant_offer":
        offer = MerchantOffer(**payload.get("offer", {}))
        source_id = target_id  # offer 发回 A，A 是 target
        _A2A_PENDING[(source_id, offer.request_id)][offer.merchant_id] = offer

        recommendation = _recommend_a2a(source_id, offer.request_id)
        if recommendation:
            _A2A_RECOMMENDED[offer.request_id] = recommendation
            notify = SignalEnvelope(
                msg_type=MsgType.ACK,
                sender_id="hub",
                payload={"type": "a2a_recommendation", "request_id": offer.request_id, "recommendation": recommendation},
            )
            await merchant_pool.send_to(source_id, notify)

        env = SignalEnvelope(msg_type=MsgType.ACK, sender_id="hub", payload={"type": "a2a_packet", "packet": packet_dict})
        ok = await merchant_pool.send_to(target_id, env)
        if not ok:
            raise ValueError("a2a_target_offline")
        return

    raise ValueError("a2a_unknown_kind")


# -- TradeMeta + Coordinator ------------------------------------------
@dataclass
class TradeMeta:
    client_id: str; status: TradeStatus; created_at: float; expire_at: float

class TradeCoordinator:
    def __init__(self, merchants, clients, db):
        self.merchants=merchants; self.clients=clients; self.db=db
        self._pending=defaultdict(dict); self._offers=defaultdict(dict)
        self._meta: Dict[str,TradeMeta]={}; self._lock=asyncio.Lock()
        self._merchant_geo: Dict[str, Optional[tuple]] = {}  # mid -> (lat, lng)
        self._executing: Dict[str, ExecuteTrade] = {}

    def _pick(self, pool, max_price):
        return sorted([o for o in pool.values() if o.viable and o.final_price<=max_price], key=lambda x:x.match_score, reverse=True)

    async def request_bundle(self, req: TradeRequest, client_id: str) -> OfferBundle:
        start=time.time(); self.db.upsert_request(req)
        first_offer_at: Optional[float] = None
        # 地理过滤：仅广播给半径内的在线商家（无坐标则广播全部）
        geo_targets: Optional[List[str]] = None
        if req.location:
            geo_targets = [
                mid for mid, coord in self._merchant_geo.items()
                if coord and _haversine_m(req.location.lat, req.location.lng, coord[0], coord[1]) <= req.location.radius_m
            ]
            if not geo_targets:
                geo_targets = None  # 无附近商家 → 降级广播全部
        async with self._lock:
            if req.request_id in self._meta:
                known=self._offers.get(req.request_id,{})
                return OfferBundle(request_id=req.request_id,offers=self._pick(known,req.max_price),total_merchants=self.merchants.count(),responded=len(known),elapsed_ms=0)
            deadline=time.time()+min(req.timeout_sec,HARD_TIMEOUT)
            self._meta[req.request_id]=TradeMeta(client_id,TradeStatus.PENDING,time.time(),deadline)
            self._pending[req.request_id]={}
        audit("trade_request",request_id=req.request_id,client_id=client_id,item=req.item_name,max_price=req.max_price)
        env_broadcast = SignalEnvelope.wrap(MsgType.INTENT_BROADCAST, "hub", req)
        if geo_targets is not None:
            # 仅广播给地理范围内的商家
            sent = []
            for mid in geo_targets:
                if await self.merchants.send_to(mid, env_broadcast):
                    sent.append(mid)
            total = len(sent)
        else:
            total = len(await self.merchants.broadcast(env_broadcast)) if self.merchants.count() else 0
        deadline=self._meta[req.request_id].expire_at
        while time.time()<deadline:
            pending_count = len(self._pending.get(req.request_id, {}))
            if pending_count > 0 and first_offer_at is None:
                first_offer_at = time.time()
            # 全部商家都响应，直接返回
            if total>0 and pending_count>=total:
                break
            # 已有首个报价后，最多再等 EARLY_RETURN_SEC 秒，降低 C 端等待
            if first_offer_at is not None and (time.time() - first_offer_at) >= EARLY_RETURN_SEC:
                break
            await asyncio.sleep(0.05)
        async with self._lock:
            got=dict(self._pending.pop(req.request_id,{})); self._offers[req.request_id]=got
            offers=self._pick(got,req.max_price); meta=self._meta.get(req.request_id)
            if meta: meta.status=TradeStatus.OFFERED if offers else TradeStatus.EXPIRED
        elapsed=round((time.time()-start)*1000,1)
        audit("offer_bundle",request_id=req.request_id,responded=len(got),valid=len(offers),elapsed_ms=elapsed)
        return OfferBundle(request_id=req.request_id,offers=offers,total_merchants=total,responded=len(got),elapsed_ms=elapsed)

    async def receive_offer(self, offer: MerchantOffer):
        async with self._lock:
            if offer.request_id in self._pending:
                self._pending[offer.request_id][offer.merchant_id]=offer

    async def wait_next_offer(self, request_id: str, seen: set[str], timeout: float = 0.8) -> Optional[MerchantOffer]:
        """SSE 使用：等待一个尚未下发过的新报价（短轮询）"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            async with self._lock:
                pool = self._pending.get(request_id, {})
                for mid, offer in pool.items():
                    key = f"{mid}:{offer.offer_id}"
                    if key not in seen:
                        seen.add(key)
                        return offer
            await asyncio.sleep(0.05)
        return None

    async def _validate(self, trade: ExecuteTrade, client_id: str) -> Tuple[bool,str]:
        async with self._lock:
            meta=self._meta.get(trade.request_id)
            if not meta: return False,"request_not_found"
            if meta.client_id!=client_id: return False,"request_client_mismatch"
            # 仅在尚未进入 OFFERED/ACCEPTED/EXECUTED 前才用过期拦截，
            # 避免用户已看到报价后因为执行时延被误判 request_expired。
            if time.time()>meta.expire_at and meta.status not in (TradeStatus.OFFERED, TradeStatus.ACCEPTED, TradeStatus.EXECUTED):
                meta.status=TradeStatus.EXPIRED
                return False,"request_expired"
            if meta.status in (TradeStatus.ACCEPTED,TradeStatus.EXECUTED): return False,"request_already_accepted"
            sel=self._offers.get(trade.request_id,{}).get(trade.merchant_id)
            if not sel: return False,"offer_merchant_not_found"
            if sel.offer_id!=trade.offer_id: return False,"offer_id_mismatch"
            if abs(sel.final_price-trade.final_price)>1e-6: return False,"offer_price_mismatch"
            meta.status=TradeStatus.ACCEPTED
        return True,"ok"

    async def execute(self, trade: ExecuteTrade, client_id: str) -> Tuple[bool,str]:
        ok,reason=await self._validate(trade,client_id)
        if not ok:
            self.db.set_failed(trade.request_id,reason)
            audit("execute_rejected",request_id=trade.request_id,reason=reason)
            return False,reason
        sent=await self.merchants.send_to(trade.merchant_id,SignalEnvelope(msg_type=MsgType.EXECUTE_TRADE,sender_id="hub",payload=trade.model_dump()))
        if not sent:
            self.db.set_failed(trade.request_id,"merchant_offline")
            return False,"merchant_offline"
        async with self._lock:
            meta=self._meta.get(trade.request_id)
            if meta: meta.status=TradeStatus.EXECUTED
            self._executing[trade.request_id] = trade
        self.db.set_executed(trade.request_id,trade.merchant_id,trade.offer_id,trade.final_price)
        await self.clients.push_status(client_id,trade.request_id,"executed",{"merchant_id":trade.merchant_id,"final_price":trade.final_price})
        audit("execute_ok",request_id=trade.request_id,client_id=client_id,merchant_id=trade.merchant_id,final_price=trade.final_price)
        return True,"ok"

    async def history(self, client_id: str, limit: int=20) -> List[dict]:
        return self.db.by_client(client_id,limit)

    async def snapshot(self, rid: str) -> dict:
        async with self._lock:
            meta=self._meta.get(rid); offers=list(self._offers.get(rid,{}).values())
        if not meta: raise KeyError(rid)
        return {"request_id":rid,"client_id":meta.client_id,"status":meta.status.value,"created_at":meta.created_at,"expire_at":meta.expire_at,"offers":[o.model_dump() for o in offers]}

    async def get_executing_trade(self, request_id: str) -> Optional[ExecuteTrade]:
        async with self._lock:
            return self._executing.get(request_id)

    async def cleanup_loop(self):
        while True:
            await asyncio.sleep(10); now=time.time()
            async with self._lock:
                old=[r for r,m in self._meta.items() if now>m.expire_at+SNAPSHOT_TTL]
                for r in old:
                    self._meta.pop(r,None)
                    self._pending.pop(r,None)
                    self._offers.pop(r,None)
                    self._executing.pop(r,None)

# -- Singletons -------------------------------------------------------
order_db      = OrderDB(DB_PATH)
merchant_pool = MerchantPool()
client_pool   = ClientPool()
coordinator   = TradeCoordinator(merchant_pool, client_pool, order_db)
rate_limiter  = RateLimiter(RATE_LIMIT)
clearing_service = ClearingService() if CLEARING_ENABLED else None
ledger_manager = LedgerManager() if LEDGER_ENABLED else None
social_coordinator = SocialCoordinator(
    similarity_threshold=SOCIAL_SIM_THRESHOLD,
    max_distance_m=SOCIAL_MAX_DISTANCE_M,
    match_cooldown_sec=SOCIAL_MATCH_COOLDOWN_SEC,
) if SOCIAL_ENABLED else None
_LAST_SETTLEMENT_REPORT: dict = {}

async def settlement_scheduler_loop():
    while True:
        try:
            if ledger_manager:
                now = datetime.now(timezone.utc)
                if now.hour == 0 and now.minute < 5:
                    report = await ledger_manager.generate_settlement_report()
                    _LAST_SETTLEMENT_REPORT.clear()
                    _LAST_SETTLEMENT_REPORT.update(report)
                    audit("settlement_report_generated", **report)
                    await asyncio.sleep(300)
                    continue
        except Exception as e:
            audit("settlement_report_failed", err=str(e))
        await asyncio.sleep(30)

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.ensure_future(merchant_pool.heartbeat_loop())
    asyncio.ensure_future(coordinator.cleanup_loop())
    asyncio.ensure_future(settlement_scheduler_loop())
    if clearing_service:
        await clearing_service.init_models()
        logger.info("[Hub] clearing service initialized")
    if ledger_manager:
        await ledger_manager.init_models()
        logger.info("[Hub] ledger service initialized")
    logger.info("[Hub] v14.3.0 started")
    yield
    logger.info("[Hub] shutdown")

app = FastAPI(title="Project Claw Signaling Hub", version="14.3.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


# -- Auth (no rate limit) ---------------------------------------------
@app.post("/api/v1/auth/client")
async def auth_client(body: dict):
    cid = str(body.get("client_id", "")).strip()
    if not cid: raise HTTPException(400, "client_id_required")
    audit("client_auth", client_id=cid)
    return {"token": jwt_issue(cid, "client"), "client_id": cid, "expires_in": JWT_EXPIRE_SEC}


@app.post("/api/v1/auth/merchant")
async def auth_merchant(body: dict):
    mid = str(body.get("merchant_id", "")).strip()
    key = str(body.get("key", "")).strip()
    promoter_id = str(body.get("promoter_id", "")).strip()
    if not mid: raise HTTPException(400, "merchant_id_required")
    if not hmac.compare_digest(key, MERCHANT_KEY): raise HTTPException(403, "wrong_merchant_key")
    if ledger_manager:
        await ledger_manager.register_merchant(mid, promoter_id=promoter_id)
    audit("merchant_auth", merchant_id=mid, promoter_id=promoter_id)
    return {"token": jwt_issue(mid, "merchant"), "merchant_id": mid, "promoter_id": promoter_id, "expires_in": JWT_EXPIRE_SEC}


# -- Public -----------------------------------------------------------
@app.get("/health")
async def health():
    return {"status": "ok", "merchants": merchant_pool.count(), "merchant_ids": merchant_pool.ids(), "ts": time.time()}


@app.get("/api/v1/system/metrics", dependencies=[Depends(rate_guard)])
async def api_system_metrics(claims: dict = Depends(bearer_claims)):
    payload = {
        "requested_by": claims["sub"],
        "merchants_online": merchant_pool.count(),
        "clearing_enabled": bool(clearing_service),
        "ledger_enabled": bool(ledger_manager),
        "social_enabled": bool(social_coordinator),
        "ts": time.time(),
    }
    if social_coordinator:
        payload["social"] = await social_coordinator.metrics_snapshot()
    return payload


@app.post("/api/v1/ledger/topup", dependencies=[Depends(rate_guard)])
async def api_ledger_topup(body: dict, claims: dict = Depends(bearer_claims)):
    if not ledger_manager:
        raise HTTPException(503, "ledger_disabled")
    if claims.get("role") != "merchant":
        raise HTTPException(403, "merchant_token_required")

    merchant_id = str(body.get("merchant_id", claims.get("sub", ""))).strip()
    if merchant_id != claims.get("sub"):
        raise HTTPException(403, "merchant_mismatch")

    amount = float(body.get("amount", 0))
    promoter_id = str(body.get("promoter_id", "")).strip()
    status = await ledger_manager.top_up(merchant_id, amount, promoter_id=promoter_id)
    await _push_billing_update(merchant_id, status)
    audit("billing_topup", merchant_id=merchant_id, amount=amount, balance=status.balance)
    return {"ok": True, "merchant_id": merchant_id, **status.model_dump()}


@app.get("/api/v1/ledger/status", dependencies=[Depends(rate_guard)])
async def api_ledger_status(claims: dict = Depends(bearer_claims)):
    if not ledger_manager:
        raise HTTPException(503, "ledger_disabled")
    if claims.get("role") != "merchant":
        raise HTTPException(403, "merchant_token_required")

    enough, status = await ledger_manager.check_balance(claims["sub"])
    return {"ok": True, "merchant_id": claims["sub"], "can_quote": enough, **status.model_dump()}


@app.get("/api/v1/ledger/settlement/latest", dependencies=[Depends(rate_guard)])
async def api_ledger_settlement_latest(claims: dict = Depends(bearer_claims)):
    if not ledger_manager:
        raise HTTPException(503, "ledger_disabled")
    return {"ok": True, "report": _LAST_SETTLEMENT_REPORT}


@app.post("/api/v1/ledger/settlement/generate", dependencies=[Depends(rate_guard)])
async def api_ledger_settlement_generate(body: dict = None, claims: dict = Depends(bearer_claims)):
    if not ledger_manager:
        raise HTTPException(503, "ledger_disabled")
    body = body or {}
    report_date = body.get("report_date")
    report = await ledger_manager.generate_settlement_report(date.fromisoformat(report_date)) if report_date else await ledger_manager.generate_settlement_report()
    _LAST_SETTLEMENT_REPORT.clear()
    _LAST_SETTLEMENT_REPORT.update(report)
    return {"ok": True, "report": report}


@app.post("/api/v1/promoter/register", dependencies=[Depends(rate_guard)])
async def api_promoter_register(body: dict, claims: dict = Depends(bearer_claims)):
    if not ledger_manager:
        raise HTTPException(503, "ledger_disabled")
    promoter_id = str(body.get("promoter_id", "")).strip()
    parent_promoter_id = str(body.get("parent_promoter_id", "")).strip()
    role_label = str(body.get("role_label", "")).strip()
    if not promoter_id:
        raise HTTPException(400, "promoter_id_required")
    wallet = await ledger_manager.register_promoter(promoter_id, parent_promoter_id=parent_promoter_id, role_label=role_label)
    return {"ok": True, "wallet": wallet}


@app.get("/api/v1/promoter/{promoter_id}/wallet", dependencies=[Depends(rate_guard)])
async def api_promoter_wallet(promoter_id: str, claims: dict = Depends(bearer_claims)):
    if not ledger_manager:
        raise HTTPException(503, "ledger_disabled")
    return {"ok": True, "wallet": await ledger_manager.wallet_snapshot(promoter_id)}


@app.post("/api/v1/ledger/settlement/pay", dependencies=[Depends(rate_guard)])
async def api_ledger_settlement_pay(body: dict, claims: dict = Depends(bearer_claims)):
    if not ledger_manager:
        raise HTTPException(503, "ledger_disabled")
    report_date = str(body.get("report_date", "")).strip()
    beneficiary_id = str(body.get("beneficiary_id", "")).strip()
    beneficiary_type = str(body.get("beneficiary_type", "promoter")).strip() or "promoter"
    if not report_date or not beneficiary_id:
        raise HTTPException(400, "report_date_and_beneficiary_id_required")
    result = await ledger_manager.mark_settlement_paid(date.fromisoformat(report_date), beneficiary_id, beneficiary_type=beneficiary_type)
    return {"ok": True, **result}


@app.post("/api/v1/promoter/withdraw", dependencies=[Depends(rate_guard)])
async def api_promoter_withdraw(body: dict, claims: dict = Depends(bearer_claims)):
    if not ledger_manager:
        raise HTTPException(503, "ledger_disabled")
    promoter_id = str(body.get("promoter_id", "")).strip()
    amount = float(body.get("amount", 0))
    account_info = body.get("account_info", {})
    note = str(body.get("note", "")).strip()
    if not promoter_id:
        raise HTTPException(400, "promoter_id_required")
    result = await ledger_manager.create_withdraw_request(promoter_id, amount, account_info=account_info, note=note)
    return {"ok": True, **result}


@app.get("/api/v1/promoter/{promoter_id}/withdraws", dependencies=[Depends(rate_guard)])
async def api_promoter_withdraws(promoter_id: str, claims: dict = Depends(bearer_claims)):
    if not ledger_manager:
        raise HTTPException(503, "ledger_disabled")
    return {"ok": True, "items": await ledger_manager.list_withdraw_requests(promoter_id)}


@app.post("/api/v1/promoter/withdraw/approve", dependencies=[Depends(rate_guard)])
async def api_promoter_withdraw_approve(body: dict, claims: dict = Depends(bearer_claims)):
    if not ledger_manager:
        raise HTTPException(503, "ledger_disabled")
    request_id = str(body.get("request_id", "")).strip()
    if not request_id:
        raise HTTPException(400, "request_id_required")
    return {"ok": True, **await ledger_manager.approve_withdraw_request(request_id)}


@app.post("/api/v1/promoter/withdraw/reject", dependencies=[Depends(rate_guard)])
async def api_promoter_withdraw_reject(body: dict, claims: dict = Depends(bearer_claims)):
    if not ledger_manager:
        raise HTTPException(503, "ledger_disabled")
    request_id = str(body.get("request_id", "")).strip()
    note = str(body.get("note", "")).strip()
    if not request_id:
        raise HTTPException(400, "request_id_required")
    return {"ok": True, **await ledger_manager.reject_withdraw_request(request_id, note=note)}


@app.post("/api/v1/promoter/withdraw/pay", dependencies=[Depends(rate_guard)])
async def api_promoter_withdraw_pay(body: dict, claims: dict = Depends(bearer_claims)):
    if not ledger_manager:
        raise HTTPException(503, "ledger_disabled")
    request_id = str(body.get("request_id", "")).strip()
    if not request_id:
        raise HTTPException(400, "request_id_required")
    return {"ok": True, **await ledger_manager.pay_withdraw_request(request_id)}


@app.get("/api/v1/merchants/online")
async def merchants_online():
    return {"online_merchants": merchant_pool.count(), "merchant_ids": merchant_pool.ids(), "ts": time.time()}


@app.post("/api/v1/social/intent", dependencies=[Depends(rate_guard)])
async def api_social_intent(intent: SocialIntent, claims: dict = Depends(bearer_claims)):
    if not social_coordinator:
        raise HTTPException(503, "social_disabled")
    intent.client_id = claims["sub"]
    events = await social_coordinator.upsert_intent(intent)
    audit("social_intent", client_id=intent.client_id, matches=len(events))
    return {"ok": True, "client_id": intent.client_id, "queued_events": len(events)}


@app.get("/api/v1/social/stream")
async def api_social_stream(claims: dict = Depends(bearer_claims)):
    if not social_coordinator:
        raise HTTPException(503, "social_disabled")
    client_id = claims["sub"]

    async def gen():
        q = await social_coordinator.register_sse(client_id)
        try:
            yield "event: ready\ndata: {\"ok\":true}\n\n"
            while True:
                evt = await q.get()
                data = evt.model_dump_json()
                yield f"event: match\ndata: {data}\n\n"
        finally:
            await social_coordinator.unregister_sse(client_id)

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/api/v1/social/metrics", dependencies=[Depends(rate_guard)])
async def api_social_metrics(claims: dict = Depends(bearer_claims)):
    if not social_coordinator:
        raise HTTPException(503, "social_disabled")
    metrics = await social_coordinator.metrics_snapshot()
    return {"ok": True, "requested_by": claims["sub"], "metrics": metrics}


# -- Protected REST ---------------------------------------------------
@app.post("/api/v1/trade/request")
async def api_trade_request(req: TradeRequest, claims: dict = Depends(bearer_claims)):
    req.client_id = claims["sub"]
    bundle = await coordinator.request_bundle(req, claims["sub"])
    return bundle.model_dump()


@app.post("/api/v1/trade/request/stream", dependencies=[Depends(rate_guard)])
async def api_trade_request_stream(req: TradeRequest, claims: dict = Depends(bearer_claims)):
    """SSE 流式报价：有新 offer 立即下发，提高首屏响应速度"""
    req.client_id = claims["sub"]

    async def event_gen():
        start = time.time()
        request_id = req.request_id
        seen: set[str] = set()

        # 先写入 meta + 广播
        async with coordinator._lock:
            if request_id not in coordinator._meta:
                deadline = time.time() + min(req.timeout_sec, HARD_TIMEOUT)
                coordinator._meta[request_id] = TradeMeta(req.client_id, TradeStatus.PENDING, time.time(), deadline)
                coordinator._pending[request_id] = {}
        coordinator.db.upsert_request(req)

        # geo 过滤复用 request_bundle 逻辑
        geo_targets: Optional[List[str]] = None
        if req.location:
            geo_targets = [
                mid for mid, coord in coordinator._merchant_geo.items()
                if coord and _haversine_m(req.location.lat, req.location.lng, coord[0], coord[1]) <= req.location.radius_m
            ]
            if not geo_targets:
                geo_targets = None

        env_broadcast = SignalEnvelope.wrap(MsgType.INTENT_BROADCAST, "hub", req)
        if geo_targets is not None:
            sent = []
            for mid in geo_targets:
                if await merchant_pool.send_to(mid, env_broadcast):
                    sent.append(mid)
            total = len(sent)
        else:
            total = len(await merchant_pool.broadcast(env_broadcast)) if merchant_pool.count() else 0

        # 首包：开始事件
        yield f"event: start\ndata: {json.dumps({'request_id': request_id, 'total_merchants': total}, ensure_ascii=False)}\n\n"

        # 持续推送 offer
        deadline = coordinator._meta[request_id].expire_at
        while time.time() < deadline:
            offer = await coordinator.wait_next_offer(request_id, seen, timeout=0.5)
            if offer is not None:
                yield f"event: offer\ndata: {json.dumps(offer.model_dump(), ensure_ascii=False)}\n\n"
            if total > 0 and len(coordinator._pending.get(request_id, {})) >= total:
                break

        # 结束：汇总并落盘同 request_bundle
        async with coordinator._lock:
            got = dict(coordinator._pending.pop(request_id, {}))
            coordinator._offers[request_id] = got
            offers = coordinator._pick(got, req.max_price)
            meta = coordinator._meta.get(request_id)
            if meta:
                meta.status = TradeStatus.OFFERED if offers else TradeStatus.EXPIRED

        elapsed = round((time.time() - start) * 1000, 1)
        bundle = OfferBundle(
            request_id=request_id,
            offers=offers,
            total_merchants=total,
            responded=len(got),
            elapsed_ms=elapsed,
        )
        audit("offer_bundle_stream", request_id=request_id, responded=len(got), valid=len(offers), elapsed_ms=elapsed)
        yield f"event: done\ndata: {json.dumps(bundle.model_dump(), ensure_ascii=False)}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@app.post("/api/v1/trade/execute", dependencies=[Depends(rate_guard)])
async def api_trade_execute(trade: ExecuteTrade, background_tasks: BackgroundTasks, promoter_id: str = "", claims: dict = Depends(bearer_claims)):
    trade.client_id = claims["sub"]
    ok, reason = await coordinator.execute(trade, claims["sub"])
    if not ok:
        raise HTTPException(409, reason)

    if not clearing_service:
        return {
            "ok": True,
            "request_id": trade.request_id,
            "merchant_id": trade.merchant_id,
            "status": TradeStatus.EXECUTED.value,
            "clearing": "disabled",
        }

    try:
        clearing = await clearing_service.create_prepay_for_trade(
            request_id=trade.request_id,
            trade_id=trade.trade_id,
            client_id=trade.client_id,
            merchant_id=trade.merchant_id,
            final_price=trade.final_price,
            promoter_id=promoter_id,
        )
    except Exception as e:
        audit("clearing_create_failed", request_id=trade.request_id, err=str(e))
        raise HTTPException(502, f"clearing_create_failed:{e}")

    return {
        "ok": True,
        "request_id": trade.request_id,
        "merchant_id": trade.merchant_id,
        "status": TradeStatus.EXECUTED.value,
        "payment": {
            "channel": "wechat_v3_partner_native",
            "out_trade_no": clearing["out_trade_no"],
            "payment_qr_url": clearing["payment_qr_url"],
            "profit_sharing": clearing["profit_sharing"],
            "route_fee_cents": clearing["route_fee_cents"],
        },
    }


@app.post("/api/v1/clearing/wechat/webhook")
async def api_clearing_wechat_webhook(request: Request, background_tasks: BackgroundTasks):
    if not clearing_service:
        raise HTTPException(503, "clearing_disabled")

    raw = await request.body()
    try:
        has_v3_headers = bool(request.headers.get("wechatpay-signature"))
        if has_v3_headers:
            event = await clearing_service.parse_wechat_webhook_v3(
                payload_bytes=raw,
                headers={k.lower(): v for k, v in request.headers.items()},
            )
        else:
            event = await clearing_service.parse_wechat_webhook(raw)
    except Exception as e:
        audit("wechat_webhook_parse_failed", err=str(e))
        raise HTTPException(400, f"invalid_wechat_webhook:{e}")

    out_trade_no = str(event.get("out_trade_no", ""))
    transaction_id = str(event.get("transaction_id", ""))
    state = str(event.get("trade_state", "")).upper()
    if not out_trade_no:
        raise HTTPException(400, "missing_out_trade_no")

    if state != "SUCCESS":
        audit("wechat_webhook_ignored", out_trade_no=out_trade_no, trade_state=state)
        return {"ok": True, "ignored": True, "trade_state": state}

    try:
        ledger_id = await clearing_service.mark_paid(
            out_trade_no=out_trade_no,
            wechat_transaction_id=transaction_id,
        )
    except KeyError:
        raise HTTPException(404, "ledger_not_found")

    background_tasks.add_task(clearing_service.settle_promoter_commission, ledger_id)
    audit("wechat_paid", out_trade_no=out_trade_no, ledger_id=ledger_id)
    return {"ok": True, "ledger_id": ledger_id, "commission_task": "queued"}


@app.get("/api/v1/orders/history", dependencies=[Depends(rate_guard)])
async def api_orders_history(limit: int = 20, claims: dict = Depends(bearer_claims)):
    limit = max(1, min(50, limit))
    return {"client_id": claims["sub"], "items": await coordinator.history(claims["sub"], limit)}


@app.get("/api/v1/trade/{request_id}", dependencies=[Depends(rate_guard)])
async def api_trade_snapshot(request_id: str, claims: dict = Depends(bearer_claims)):
    try:
        snap = await coordinator.snapshot(request_id)
        if snap.get("client_id") != claims["sub"]: raise HTTPException(403, "not_your_order")
        return snap
    except KeyError: raise HTTPException(404, "request_not_found")


@app.get("/api/v1/a2a/recommend/{request_id}")
async def api_a2a_recommend(request_id: str):
    data = _A2A_RECOMMENDED.get(request_id)
    if not data:
        raise HTTPException(404, "recommendation_not_ready")
    return data



class A2ARequestBody(BaseModel):
    source_id: str = Field(...)
    target_id: str = Field(...)
    trade_request: dict = Field(...)


@app.post("/api/v1/a2a/request")
async def api_a2a_request(body: A2ARequestBody, claims: dict = Depends(bearer_claims)):
    if claims.get("role") != "merchant" or claims.get("sub") != body.source_id:
        raise HTTPException(403, "merchant_token_required")

    packet = build_packet(
        source_id=body.source_id,
        target_id=body.target_id,
        msg_type="trade_request",
        payload={"kind": "trade_request", "trade_request": body.trade_request},
    )
    env = SignalEnvelope(msg_type=MsgType.ACK, sender_id="hub", payload={"type": "a2a_packet", "packet": packet.model_dump()})
    ok = await merchant_pool.send_to(body.target_id, env)
    if not ok:
        raise HTTPException(404, "target_merchant_offline")
    return {"ok": True, "packet_id": packet.header.packet_id}


async def _push_billing_update(merchant_id: str, status: BillingStatus, event: Optional[dict] = None):
    if not merchant_id:
        return
    payload = {
        "type": "billing_update",
        "merchant_id": merchant_id,
        "balance": status.balance,
        "is_frozen": status.is_frozen,
        "currency_unit": status.currency_unit,
        "ts": time.time(),
    }
    if event:
        payload["transaction"] = event
    env = SignalEnvelope(msg_type=MsgType.BILLING_UPDATE, sender_id="hub", payload=payload)
    await merchant_pool.send_to(merchant_id, env)


async def _handle_execute_ack_billing(merchant_id: str, payload: dict):
    if not ledger_manager:
        return
    if payload.get("type") != "execute_result":
        return
    if not bool(payload.get("ok", False)):
        return

    rid = str(payload.get("request_id", "")).strip()
    if not rid:
        return

    trade = await coordinator.get_executing_trade(rid)
    if not trade:
        audit("billing_skip", request_id=rid, merchant_id=merchant_id, reason="executing_trade_not_found")
        return

    try:
        amount = ledger_manager.compute_deduct_amount(trade.final_price)
        status, txn = await ledger_manager.deduct_token(merchant_id=merchant_id, amount=amount, trade_id=trade.trade_id)
        await _push_billing_update(merchant_id, status, event=txn.model_dump())
        audit(
            "billing_deduct_ok",
            request_id=rid,
            trade_id=trade.trade_id,
            merchant_id=merchant_id,
            amount=amount,
            balance=status.balance,
            currency_unit=status.currency_unit,
        )
    except Exception as e:
        audit("billing_deduct_failed", request_id=rid, trade_id=trade.trade_id, merchant_id=merchant_id, err=str(e))


# -- WebSocket --------------------------------------------------------
@app.websocket("/ws/merchant/{merchant_id}")
async def merchant_ws(ws: WebSocket, merchant_id: str):
    token = ws.query_params.get("token", "")
    try:
        ws_verify(token, "merchant", merchant_id)
    except HTTPException as e:
        logger.warning(f"[WS] merchant auth rejected mid={merchant_id} detail={e.detail}")
        await ws.close(code=4403)
        return
    # 从 query 参数读取商家坐标（可选）
    try:
        m_lat = float(ws.query_params.get("lat", ""))
        m_lng = float(ws.query_params.get("lng", ""))
        coordinator._merchant_geo[merchant_id] = (m_lat, m_lng)
        logger.info(f"[WS] merchant geo registered mid={merchant_id} lat={m_lat} lng={m_lng}")
    except (ValueError, TypeError):
        coordinator._merchant_geo[merchant_id] = None
    await merchant_pool.register(merchant_id, ws)
    try:
        while True:
            env = SignalEnvelope.model_validate_json(await ws.receive_text())
            if env.msg_type == MsgType.HEARTBEAT:
                merchant_pool.update_pong(merchant_id)
                # heartbeat payload 可携带实时坐标更新
                p = env.payload
                if "lat" in p and "lng" in p:
                    try:
                        coordinator._merchant_geo[merchant_id] = (float(p["lat"]), float(p["lng"]))
                    except (ValueError, TypeError):
                        pass
            elif env.msg_type == MsgType.MERCHANT_OFFER:
                if ledger_manager:
                    enough, status = await ledger_manager.check_balance(merchant_id)
                    if not enough:
                        await _push_billing_update(merchant_id, status)
                        await merchant_pool.send_to(
                            merchant_id,
                            SignalEnvelope(
                                msg_type=MsgType.ERROR,
                                sender_id="hub",
                                payload={
                                    "type": "billing_insufficient",
                                    "merchant_id": merchant_id,
                                    "balance": status.balance,
                                    "currency_unit": status.currency_unit,
                                    "is_frozen": status.is_frozen,
                                    "reason": "insufficient_token_for_quote",
                                },
                            ),
                        )
                        continue
                await coordinator.receive_offer(MerchantOffer(**env.payload))
            elif env.msg_type == MsgType.ACK and env.payload.get("type") == "a2a_packet":
                try:
                    await _handle_a2a_packet_from_merchant(merchant_id, env.payload.get("packet", {}))
                except Exception as e:
                    err = SignalEnvelope(
                        msg_type=MsgType.ERROR,
                        sender_id="hub",
                        payload={"type": "a2a_packet_error", "error": str(e), "ts": time.time()},
                    )
                    await merchant_pool.send_to(merchant_id, err)
            elif env.msg_type == MsgType.ACK and env.payload.get("type") == "execute_result":
                rid = str(env.payload.get("request_id", ""))
                ok = bool(env.payload.get("ok", False))
                reason = str(env.payload.get("reason", ""))
                client_id = str(env.payload.get("client_id", ""))
                if rid and client_id:
                    status = "executed_device_ok" if ok else "executed_device_failed"
                    await client_pool.push_status(client_id, rid, status, {
                        "merchant_id": merchant_id,
                        "reason": reason,
                    })
                await _handle_execute_ack_billing(merchant_id, env.payload)
    except WebSocketDisconnect: pass
    finally:
        coordinator._merchant_geo.pop(merchant_id, None)
        await merchant_pool.unregister(merchant_id)


@app.websocket("/ws/client/{client_id}")
async def client_ws(ws: WebSocket, client_id: str):
    token = ws.query_params.get("token", "")
    try:
        ws_verify(token, "client", client_id)
    except HTTPException as e:
        logger.warning(f"[WS] client auth rejected cid={client_id} detail={e.detail}")
        await ws.close(code=4403)
        return
    await client_pool.register(client_id, ws)
    try:
        while True:
            env = SignalEnvelope.model_validate_json(await ws.receive_text())
            if env.msg_type == MsgType.TRADE_REQUEST:
                req = TradeRequest(**env.payload)
                req.client_id = client_id
                bundle = await coordinator.request_bundle(req, client_id)
                await client_pool.send_to(client_id, SignalEnvelope.wrap(MsgType.OFFER_BUNDLE, "hub", bundle))
            elif env.msg_type == MsgType.EXECUTE_TRADE:
                trade = ExecuteTrade(**env.payload)
                trade.client_id = client_id
                ok, reason = await coordinator.execute(trade, client_id)
                payload = {"request_id": trade.request_id, "status": TradeStatus.EXECUTED.value} if ok else {"code": reason, "request_id": trade.request_id}
                await client_pool.send_to(client_id, SignalEnvelope(msg_type=MsgType.ACK if ok else MsgType.ERROR, sender_id="hub", payload=payload))
    except WebSocketDisconnect: pass
    finally: await client_pool.unregister(client_id)
