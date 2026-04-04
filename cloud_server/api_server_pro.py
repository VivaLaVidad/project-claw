from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncGenerator

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from jose import JWTError, jwt

from cloud_server.persona_builder_routes import router as persona_builder_router
from cloud_server.a2a_arena_routes import router as a2a_arena_router

try:
    from cloud_server.db import init_db_schema
except ModuleNotFoundError as e:
    if e.name != "cloud_server":
        raise
    from db import init_db_schema

APP_NAME = "Project Claw C-API"
JWT_SECRET = os.getenv("HUB_JWT_SECRET", "claw-change-in-prod")
JWT_ALG = "HS256"
ACCESS_EXPIRE_SEC = int(os.getenv("ACCESS_TOKEN_EXPIRE_SEC", "3600"))
MERCHANT_LOGIN_KEY = os.getenv("MERCHANT_LOGIN_KEY", "123456")
MAX_TRADE_SNAPSHOTS = int(os.getenv("MAX_TRADE_SNAPSHOTS", "300"))
ENV_NAME = os.getenv("ENV", "dev").lower()
ALLOWED_ORIGINS = [x.strip() for x in os.getenv("ALLOWED_ORIGINS", "*").split(",") if x.strip()]
LOGIN_WINDOW_SEC = int(os.getenv("LOGIN_WINDOW_SEC", "60"))
LOGIN_MAX_ATTEMPTS = int(os.getenv("LOGIN_MAX_ATTEMPTS", "10"))
MAX_DEMAND_TEXT_LEN = int(os.getenv("MAX_DEMAND_TEXT_LEN", "500"))

app = FastAPI(title=APP_NAME, version="2.2.1")
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
app.include_router(persona_builder_router)
app.include_router(a2a_arena_router)

if ENV_NAME == "prod" and JWT_SECRET == "claw-change-in-prod":
    raise RuntimeError("HUB_JWT_SECRET must be set in production")
if ENV_NAME == "prod" and MERCHANT_LOGIN_KEY == "123456":
    raise RuntimeError("MERCHANT_LOGIN_KEY must be changed in production")

SEEDED_MERCHANTS = [
    {"merchant_id": "box-001", "display_name": "李记面馆", "category": "面馆", "address": "国贸店", "accepting": True},
    {"merchant_id": "box-002", "display_name": "阿强麻辣烫", "category": "麻辣烫", "address": "望京店", "accepting": True},
    {"merchant_id": "box-003", "display_name": "陈记盖饭", "category": "盖饭", "address": "中关村店", "accepting": True},
    {"merchant_id": "box-004", "display_name": "早八轻食", "category": "轻食", "address": "三里屯店", "accepting": True},
    {"merchant_id": "box-005", "display_name": "老王水饺", "category": "水饺", "address": "双井店", "accepting": True},
]
CUSTOM_MERCHANTS: dict[str, dict[str, Any]] = {}
TRADE_SNAPSHOTS: dict[str, dict[str, Any]] = {}
LOGIN_ATTEMPTS: dict[str, deque[float]] = {}


def _issue_token(sub: str, token_type: str, exp_sec: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": sub, "typ": token_type, "iat": int(now.timestamp()), "exp": int((now + timedelta(seconds=exp_sec)).timestamp()), "jti": uuid.uuid4().hex}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def _decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except JWTError:
        raise HTTPException(status_code=401, detail="invalid_token")


def _bearer_claims(authorization: str = Header(default="")) -> dict[str, Any]:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing_bearer_token")
    claims = _decode_token(authorization[7:])
    if claims.get("typ") != "access":
        raise HTTPException(status_code=401, detail="access_token_required")
    return claims


def _merchant_claims(authorization: str = Header(default="")) -> dict[str, Any]:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing_bearer_token")
    claims = _decode_token(authorization[7:])
    if claims.get("typ") != "merchant_access":
        raise HTTPException(status_code=401, detail="merchant_token_required")
    return claims


def _put_trade_snapshot(request_id: str, snapshot: dict[str, Any]) -> None:
    TRADE_SNAPSHOTS[request_id] = snapshot
    if len(TRADE_SNAPSHOTS) > MAX_TRADE_SNAPSHOTS:
        oldest = next(iter(TRADE_SNAPSHOTS))
        TRADE_SNAPSHOTS.pop(oldest, None)




def _assert_login_rate_limit(subject: str) -> None:
    now = time.time()
    bucket = LOGIN_ATTEMPTS.setdefault(subject, deque())
    while bucket and (now - bucket[0] > LOGIN_WINDOW_SEC):
        bucket.popleft()
    if len(bucket) >= LOGIN_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="too_many_login_attempts")
    bucket.append(now)


def _trim_demand_text(value: Any) -> str:
    txt = str(value or "").strip()
    return txt[:MAX_DEMAND_TEXT_LEN]


def _all_merchants() -> list[dict[str, Any]]:
    merged = {m["merchant_id"]: dict(m) for m in SEEDED_MERCHANTS}
    for mid, p in CUSTOM_MERCHANTS.items():
        merged[mid] = {
            "merchant_id": mid,
            "display_name": p.get("display_name") or mid,
            "category": p.get("category") or "综合服务",
            "address": p.get("address") or "线上可服务",
            "contact_phone": p.get("contact_phone") or "",
            "tags": p.get("tags") or "",
            "note": p.get("note") or "",
            "accepting": bool(p.get("accepting", True)),
            "today_revenue": float(p.get("today_revenue", 188.0)),
            "today_order_count": int(p.get("today_order_count", 6)),
            "pending_count": int(p.get("pending_count", 2)),
        }
    return list(merged.values())


@app.on_event("startup")
async def _startup():
    await init_db_schema()


@app.get("/health")
async def health():
    online = len([m for m in _all_merchants() if m.get("accepting", True)])
    return {"status": "ok", "service": APP_NAME, "merchants": online, "ts": time.time()}


@app.post("/api/v1/auth/client")
async def api_auth_client(body: dict[str, Any]):
    client_id = str(body.get("client_id") or body.get("code") or "").strip()
    if not client_id:
        raise HTTPException(status_code=400, detail="client_id_required")
    access = _issue_token(client_id, "access", ACCESS_EXPIRE_SEC)
    refresh = _issue_token(client_id, "refresh", ACCESS_EXPIRE_SEC)
    return {"token": access, "access_jwt": access, "refresh_jwt": refresh, "client_id": client_id, "expires_in": ACCESS_EXPIRE_SEC}


@app.get("/api/v1/merchants/online")
async def api_merchants_online():
    items = [{"merchant_id": m["merchant_id"], "display_name": m.get("display_name") or m["merchant_id"], "category": m.get("category") or "综合服务", "address": m.get("address") or "线上可服务"} for m in _all_merchants() if m.get("accepting", True)]
    return {"online_merchants": len(items), "items": items, "ts": time.time()}


@app.post("/api/v1/auth/merchant")
async def api_auth_merchant(body: dict[str, Any]):
    mid = str(body.get("merchant_id") or "").strip()
    key = str(body.get("key") or "").strip()
    _assert_login_rate_limit(mid or "unknown")
    if not mid or not key:
        raise HTTPException(status_code=400, detail="merchant_id_and_key_required")
    if key != MERCHANT_LOGIN_KEY:
        raise HTTPException(status_code=401, detail="invalid_merchant_key")
    p = CUSTOM_MERCHANTS.get(mid, {})
    p.setdefault("display_name", mid)
    p.setdefault("category", "综合服务")
    p.setdefault("address", "线上可服务")
    p.setdefault("accepting", True)
    CUSTOM_MERCHANTS[mid] = p
    token = _issue_token(mid, "merchant_access", ACCESS_EXPIRE_SEC)
    return {"token": token, "merchant_id": mid, "expires_in": ACCESS_EXPIRE_SEC}


@app.websocket("/ws/merchant/{merchant_id}")
async def ws_merchant(merchant_id: str, websocket: WebSocket):
    token = websocket.query_params.get("token") or ""
    if not token:
        await websocket.close(code=1008)
        return
    claims = _decode_token(token)
    if claims.get("typ") != "merchant_access" or str(claims.get("sub") or "") != merchant_id:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        while True:
            _ = await websocket.receive_text()
            await websocket.send_text(json.dumps({"msg_type": "heartbeat", "payload": {"type": "pong", "ts": time.time()}}, ensure_ascii=False))
    except WebSocketDisconnect:
        return


@app.get("/api/v1/merchant/dashboard")
async def api_merchant_dashboard(claims: dict[str, Any] = Depends(_merchant_claims)):
    mid = str(claims.get("sub") or "")
    p = CUSTOM_MERCHANTS.get(mid, {})
    return {"merchant_id": mid, "today_revenue": float(p.get("today_revenue", 188.0)), "today_order_count": int(p.get("today_order_count", 6)), "pending_count": int(p.get("pending_count", 2)), "last_update": time.time()}


@app.post("/api/v1/merchant/status")
async def api_merchant_status(body: dict[str, Any], claims: dict[str, Any] = Depends(_merchant_claims)):
    mid = str(claims.get("sub") or "")
    p = CUSTOM_MERCHANTS.get(mid, {})
    p["accepting"] = bool(body.get("accepting", True))
    CUSTOM_MERCHANTS[mid] = p
    return {"ok": True, "merchant_id": mid, "accepting": p["accepting"]}


@app.get("/api/v1/merchant/orders")
async def api_merchant_orders(claims: dict[str, Any] = Depends(_merchant_claims)):
    mid = str(claims.get("sub") or "")
    now = int(time.time())
    return {"items": [{"order_id": f"o-{now}-1", "merchant_id": mid, "item_name": "招牌牛肉面", "final_price": 22.0, "status": "pending"}, {"order_id": f"o-{now}-2", "merchant_id": mid, "item_name": "水饺", "final_price": 18.0, "status": "done"}]}


@app.get("/api/v1/merchant/wallet")
async def api_merchant_wallet(claims: dict[str, Any] = Depends(_merchant_claims)):
    mid = str(claims.get("sub") or "")
    return {"merchant_id": mid, "balance": 1288.5, "today_income": 188.0, "pending_settlement": 96.0}


@app.get("/api/v1/merchant/device-status")
async def api_merchant_device_status(claims: dict[str, Any] = Depends(_merchant_claims)):
    mid = str(claims.get("sub") or "")
    p = CUSTOM_MERCHANTS.get(mid, {})
    return {"merchant_id": mid, "ws_online": True, "accepting": bool(p.get("accepting", True))}


@app.get("/api/v1/merchant/edge-last-frame")
@app.get("/api/v1/merchant/edge_last_frame")
async def api_merchant_edge_last_frame(_: dict[str, Any] = Depends(_merchant_claims)):
    return {"has_frame": False, "image_data_url": "", "updated_at": time.time()}


@app.get("/api/v1/merchant/profile")
async def api_merchant_profile(claims: dict[str, Any] = Depends(_merchant_claims)):
    mid = str(claims.get("sub") or "")
    p = CUSTOM_MERCHANTS.get(mid, {})
    return {"merchant_id": mid, "display_name": p.get("display_name") or mid, "category": p.get("category") or "综合服务", "address": p.get("address") or "线上可服务", "contact_phone": p.get("contact_phone") or "", "tags": p.get("tags") or "", "note": p.get("note") or ""}


@app.post("/api/v1/merchant/profile")
async def api_merchant_save_profile(body: dict[str, Any], claims: dict[str, Any] = Depends(_merchant_claims)):
    mid = str(claims.get("sub") or "")
    p = CUSTOM_MERCHANTS.get(mid, {})
    p.update({"display_name": str(body.get("display_name") or mid), "category": str(body.get("category") or "综合服务"), "address": str(body.get("address") or "线上可服务"), "contact_phone": str(body.get("contact_phone") or ""), "tags": str(body.get("tags") or ""), "note": str(body.get("note") or ""), "accepting": bool(p.get("accepting", True))})
    CUSTOM_MERCHANTS[mid] = p
    return {"merchant_id": mid, "display_name": p["display_name"], "category": p["category"], "address": p["address"], "contact_phone": p["contact_phone"], "tags": p["tags"], "note": p["note"]}




@app.post("/api/v1/merchant/mock/bulk_create")
async def api_merchant_mock_bulk_create(body: dict[str, Any], _: dict[str, Any] = Depends(_merchant_claims)):
    count = max(1, min(50, int(body.get("count") or 10)))
    categories = ["面馆", "麻辣烫", "盖饭", "轻食", "水饺", "烧烤"]
    zones = ["国贸", "望京", "中关村", "双井", "三里屯", "西二旗"]
    created_ids: list[str] = []
    start_idx = len([k for k in CUSTOM_MERCHANTS.keys() if str(k).startswith("merchant-auto-")]) + 1
    for i in range(count):
        idx = start_idx + i
        mid = f"merchant-auto-{idx:03d}"
        CUSTOM_MERCHANTS[mid] = {
            "display_name": f"自动商家{idx:03d}",
            "category": categories[idx % len(categories)],
            "address": f"{zones[idx % len(zones)]}店",
            "contact_phone": "",
            "tags": "自动生成,可接单",
            "note": "bulk-created",
            "accepting": True,
            "today_revenue": float(90 + idx * 3),
            "today_order_count": int(3 + (idx % 7)),
            "pending_count": int(idx % 4),
        }
        created_ids.append(mid)
    return {"ok": True, "created": len(created_ids), "merchant_ids": created_ids}


@app.post("/api/v1/merchant/mock/clear")
async def api_merchant_mock_clear(_: dict[str, Any] = Depends(_merchant_claims)):
    removed = 0
    for mid in list(CUSTOM_MERCHANTS.keys()):
        if str(mid).startswith("merchant-auto-"):
            CUSTOM_MERCHANTS.pop(mid, None)
            removed += 1
    return {"ok": True, "removed": removed}


@app.post("/api/v1/trade/request")
async def api_trade_request(body: dict[str, Any], _: dict[str, Any] = Depends(_bearer_claims)):
    rid = str(body.get("request_id") or f"r-{uuid.uuid4().hex[:8]}")
    _put_trade_snapshot(rid, {"request_id": rid, "offers": []})
    return {"ok": True, "request_id": rid}


@app.post("/api/v1/trade/request/stream")
async def api_trade_request_stream(body: dict[str, Any], _: dict[str, Any] = Depends(_bearer_claims)):
    rid = str(body.get("request_id") or f"r-{uuid.uuid4().hex[:8]}")
    item = str(body.get("item_name") or "商品")
    demand = _trim_demand_text(body.get("demand_text"))
    max_price = max(1, float(body.get("max_price") or 20))
    merchants = [m for m in _all_merchants() if m.get("accepting", True)] or [{"merchant_id": "box-001", "display_name": "示例商家", "accepting": True}]

    async def _event_gen() -> AsyncGenerator[str, None]:
        yield f"event: start\ndata: {json.dumps({'request_id': rid, 'total_merchants': len(merchants)}, ensure_ascii=False)}\n\n"
        offers: list[dict[str, Any]] = []
        for idx, m in enumerate(merchants[:8]):
            await asyncio.sleep(0.25)
            yield f"event: dialogue\ndata: {json.dumps({'role': 'buyer_agent', 'merchant_id': m['merchant_id'], 'text': f'C端Agent：目标商品 {item}，预算上限 ¥{max_price:.0f}，请给出最优报价。'}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.25)
            factor = 0.66 + (idx * 0.05)
            price = min(max_price, round(max(1.0, max_price * min(0.96, factor)), 2))
            txt = f"B端Agent({m.get('display_name') or m['merchant_id']})：{item} 可以 ¥{price}，{demand or '可快速出餐'}。"
            yield f"event: dialogue\ndata: {json.dumps({'role': 'merchant_agent', 'merchant_id': m['merchant_id'], 'text': txt}, ensure_ascii=False)}\n\n"
            offer = {"request_id": rid, "merchant_id": m["merchant_id"], "offer_id": f"of-{uuid.uuid4().hex[:8]}", "item_name": item, "final_price": price, "eta_minutes": 15 + idx, "match_score": max(70, 96 - idx * 3), "reply_text": f"{m.get('display_name') or m['merchant_id']}：{item} {price}元可做。"}
            offers.append(offer)
            yield f"event: offer\ndata: {json.dumps(offer, ensure_ascii=False)}\n\n"
        offers.sort(key=lambda x: float(x.get("final_price", 999999)))
        done = {"request_id": rid, "offers": offers, "selected_offer_id": offers[0]["offer_id"] if offers else ""}
        _put_trade_snapshot(rid, done)
        yield f"event: done\ndata: {json.dumps(done, ensure_ascii=False)}\n\n"

    return StreamingResponse(_event_gen(), media_type="text/event-stream")


@app.get("/api/v1/trade/{request_id}")
async def api_trade_snapshot(request_id: str, _: dict[str, Any] = Depends(_bearer_claims)):
    return TRADE_SNAPSHOTS.get(request_id) or {"request_id": request_id, "offers": []}


@app.post("/api/v1/trade/execute")
async def api_trade_execute(body: dict[str, Any], _: dict[str, Any] = Depends(_bearer_claims)):
    rid = str(body.get("request_id") or "")
    oid = str(body.get("offer_id") or "")
    if not rid or not oid:
        raise HTTPException(status_code=400, detail="request_id_and_offer_id_required")
    return {"ok": True, "trade_id": f"t-{uuid.uuid4().hex[:10]}", "request_id": rid, "offer_id": oid, "merchant_id": str(body.get('merchant_id') or ''), "final_price": float(body.get('final_price') or 0), "paid": True}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8765")), reload=False)






