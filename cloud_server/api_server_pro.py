"""cloud_server/api_server_pro.py
C 端微信小程序工业级 API 网关（鉴权 + 流式撮合）
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncGenerator, Optional

import httpx
import redis.asyncio as redis
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from jose import jwt, JWTError
from sqlalchemy import select

from cloud_server.data_models import ClientORM
from cloud_server.db import init_db_schema, session_scope


APP_NAME = "Project Claw C-API"
JWT_SECRET = os.getenv("HUB_JWT_SECRET", "claw-change-in-prod")
JWT_ALG = "HS256"
ACCESS_EXPIRE_SEC = int(os.getenv("ACCESS_TOKEN_EXPIRE_SEC", "3600"))
REFRESH_EXPIRE_SEC = int(os.getenv("REFRESH_TOKEN_EXPIRE_SEC", "2592000"))

WECHAT_APPID = os.getenv("WECHAT_APPID", "")
WECHAT_SECRET = os.getenv("WECHAT_SECRET", "")
WECHAT_LOGIN_URL = "https://api.weixin.qq.com/sns/jscode2session"
WECHAT_MOCK_LOGIN = os.getenv("WECHAT_MOCK_LOGIN", "1") == "1"

REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
REDIS_OFFER_CHANNEL = os.getenv("REDIS_OFFER_CHANNEL", "claw:merchant_offer")
RATE_LIMIT_PER_MIN = 10


app = FastAPI(title=APP_NAME, version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

redis_client = redis.from_url(REDIS_URL, decode_responses=True)


def _now_ts() -> int:
    return int(time.time())


def _issue_token(sub: str, token_type: str, exp_sec: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "typ": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=exp_sec)).timestamp()),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def _decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"invalid_token:{e}")


async def _rate_limit_guard(client_key: str, route: str):
    key = f"rl:{route}:{client_key}"
    now = _now_ts()
    win_start = now - 60
    pipe = redis_client.pipeline()
    pipe.zremrangebyscore(key, 0, win_start)
    member = f"{now}:{uuid.uuid4().hex[:8]}"
    pipe.zadd(key, {member: now})
    pipe.zcard(key)
    pipe.expire(key, 90)
    _, _, count, _ = await pipe.execute()
    if int(count) > RATE_LIMIT_PER_MIN:
        raise HTTPException(status_code=429, detail="rate_limit_exceeded")


async def _wechat_exchange_code(code: str) -> str:
    if WECHAT_MOCK_LOGIN and (not WECHAT_APPID or not WECHAT_SECRET):
        # 本地/测试兜底：由 code 稳定映射 openid
        digest = hashlib.sha256(code.encode("utf-8")).hexdigest()[:24]
        return f"mock_openid_{digest}"

    params = {
        "appid": WECHAT_APPID,
        "secret": WECHAT_SECRET,
        "js_code": code,
        "grant_type": "authorization_code",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(WECHAT_LOGIN_URL, params=params)
        data = resp.json()

    if data.get("errcode"):
        raise HTTPException(status_code=401, detail=f"wechat_auth_failed:{data.get('errmsg', '')}")

    openid = str(data.get("openid", "")).strip()
    if not openid:
        raise HTTPException(status_code=401, detail="wechat_openid_missing")
    return openid


async def _silent_register_or_login(openid: str) -> dict[str, Any]:
    async with session_scope() as session:
        row = await session.scalar(select(ClientORM).where(ClientORM.wechat_openid == openid))
        if row is None:
            row = ClientORM(
                client_id=f"c_{uuid.uuid4().hex[:16]}",
                wechat_openid=openid,
                persona_vector={},
                risk_score=0.0,
                created_at=time.time(),
                updated_at=time.time(),
            )
            session.add(row)
            await session.flush()
        else:
            row.updated_at = time.time()

        client_id = row.client_id

    access = _issue_token(client_id, "access", ACCESS_EXPIRE_SEC)
    refresh = _issue_token(client_id, "refresh", REFRESH_EXPIRE_SEC)
    return {
        "client_id": client_id,
        "openid": openid,
        "access_jwt": access,
        "refresh_jwt": refresh,
        "access_expires_in": ACCESS_EXPIRE_SEC,
        "refresh_expires_in": REFRESH_EXPIRE_SEC,
    }


def _bearer_claims(authorization: str = Header(default="")) -> dict[str, Any]:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing_bearer_token")
    claims = _decode_token(authorization[7:])
    if claims.get("typ") != "access":
        raise HTTPException(status_code=401, detail="access_token_required")
    return claims


@app.on_event("startup")
async def _startup():
    await init_db_schema()


@app.post("/api/v1/auth/wechat_login")
async def api_wechat_login(body: dict[str, Any]):
    code = str(body.get("code", "")).strip()
    if not code:
        raise HTTPException(status_code=400, detail="code_required")
    await _rate_limit_guard(client_key=hashlib.md5(code.encode()).hexdigest()[:12], route="wechat_login")
    openid = await _wechat_exchange_code(code)
    return {"ok": True, **await _silent_register_or_login(openid)}


@app.get("/api/v1/trade/stream_quotes")
async def api_trade_stream_quotes(
    request_id: str = Query(default=""),
    claims: dict[str, Any] = Depends(_bearer_claims),
):
    client_id = str(claims.get("sub", ""))
    if not client_id:
        raise HTTPException(status_code=401, detail="invalid_client")
    await _rate_limit_guard(client_key=client_id, route="stream_quotes")

    async def _event_gen() -> AsyncGenerator[str, None]:
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(REDIS_OFFER_CHANNEL)
        try:
            yield f"event: THOUGHT\ndata: {json.dumps({'text': '正在连接商户报价通道...', 'ts': time.time()}, ensure_ascii=False)}\n\n"
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if not msg:
                    yield "event: THOUGHT\ndata: {\"text\":\"正在与周边商家实时议价...\"}\n\n"
                    continue
                try:
                    payload = json.loads(msg["data"])
                except Exception:
                    continue

                target_client = str(payload.get("client_id", ""))
                if target_client and target_client != client_id:
                    continue
                if request_id and str(payload.get("request_id", "")) != request_id:
                    continue

                evt_type = str(payload.get("type", "OFFER")).upper()
                if evt_type not in {"THOUGHT", "OFFER", "MATCH_SUCCESS"}:
                    evt_type = "OFFER"

                if evt_type == "THOUGHT":
                    data = {
                        "request_id": payload.get("request_id", request_id),
                        "text": payload.get("text", "正在与李记拉面砍价..."),
                        "ts": time.time(),
                    }
                elif evt_type == "MATCH_SUCCESS":
                    data = {
                        "request_id": payload.get("request_id", request_id),
                        "merchant_id": payload.get("merchant_id", ""),
                        "final_price": payload.get("final_price", 0),
                        "trade_id": payload.get("trade_id", ""),
                        "ts": time.time(),
                    }
                else:
                    data = {
                        "request_id": payload.get("request_id", request_id),
                        "merchant_id": payload.get("merchant_id", ""),
                        "offer_id": payload.get("offer_id", ""),
                        "item_name": payload.get("item_name", ""),
                        "final_price": payload.get("final_price", 0),
                        "eta_minutes": payload.get("eta_minutes", None),
                        "score": payload.get("match_score", None),
                        "ts": time.time(),
                    }

                yield f"event: {evt_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        finally:
            await pubsub.unsubscribe(REDIS_OFFER_CHANNEL)
            await pubsub.close()

    return StreamingResponse(_event_gen(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("cloud_server.api_server_pro:app", host="0.0.0.0", port=int(os.getenv("PORT", "8780")), reload=False)
