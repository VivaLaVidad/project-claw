from __future__ import annotations

import asyncio
import json
import os
import time
from collections import defaultdict
from typing import Dict, Optional

import redis.asyncio as redis
from fastapi import WebSocket

from shared.claw_protocol import MsgType, SignalEnvelope


REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
WS_STATE_PREFIX = "claw:ws:merchant:"
A2A_PENDING_PREFIX = "claw:a2a:pending:"
PUBSUB_CHAN = "claw:merchant:broadcast"
A2A_TTL_SEC = float(os.getenv("A2A_WINDOW_TTL_SEC", "3.0"))


class WSConnectionManager:
    ping_interval = 20.0
    pong_timeout = 10.0

    def __init__(self):
        self._redis = redis.from_url(REDIS_URL, decode_responses=True)
        self._local_conns: Dict[str, WebSocket] = {}
        self._last_pong: Dict[str, float] = defaultdict(lambda: 0.0)
        self._lock = asyncio.Lock()
        self._subscriber_task: Optional[asyncio.Task] = None

    async def start(self):
        if self._subscriber_task and not self._subscriber_task.done():
            return
        self._subscriber_task = asyncio.create_task(self._subscriber_loop())

    async def stop(self):
        if self._subscriber_task:
            self._subscriber_task.cancel()
        await self._redis.close()

    async def register(self, merchant_id: str, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self._local_conns[merchant_id] = ws
            self._last_pong[merchant_id] = time.time()
        await self._redis.set(f"{WS_STATE_PREFIX}{merchant_id}", str(time.time()), ex=60)

    async def unregister(self, merchant_id: str):
        async with self._lock:
            self._local_conns.pop(merchant_id, None)
            self._last_pong.pop(merchant_id, None)
        await self._redis.delete(f"{WS_STATE_PREFIX}{merchant_id}")

    async def update_pong(self, merchant_id: str):
        self._last_pong[merchant_id] = time.time()
        await self._redis.set(f"{WS_STATE_PREFIX}{merchant_id}", str(time.time()), ex=60)

    # 兼容旧调用（本实例在线连接）
    def count(self) -> int:
        return len(self._local_conns)

    def ids(self) -> list[str]:
        return list(self._local_conns.keys())

    # 集群视角（Redis 全局在线状态）
    async def global_count(self) -> int:
        n = 0
        async for _ in self._redis.scan_iter(f"{WS_STATE_PREFIX}*"):
            n += 1
        return n

    async def global_ids(self) -> list[str]:
        out = []
        async for key in self._redis.scan_iter(f"{WS_STATE_PREFIX}*"):
            out.append(key.replace(WS_STATE_PREFIX, ""))
        return out

    async def send_to(self, merchant_id: str, env: SignalEnvelope) -> bool:
        ws = self._local_conns.get(merchant_id)
        if ws is not None:
            try:
                await ws.send_text(env.model_dump_json())
                return True
            except Exception:
                await self.unregister(merchant_id)
                return False
        await self._redis.publish(PUBSUB_CHAN, json.dumps({"merchant_id": merchant_id, "env": env.model_dump()}))
        return True

    async def broadcast(self, env: SignalEnvelope):
        mids = self.ids()
        payload = {"merchant_id": "*", "env": env.model_dump()}
        await self._redis.publish(PUBSUB_CHAN, json.dumps(payload))
        return mids

    async def set_a2a_pending(self, source_id: str, request_id: str, payload: dict):
        key = f"{A2A_PENDING_PREFIX}{source_id}:{request_id}"
        await self._redis.set(key, json.dumps(payload, ensure_ascii=False), ex=max(1, int(A2A_TTL_SEC)))

    async def get_a2a_pending(self, source_id: str, request_id: str) -> Optional[dict]:
        key = f"{A2A_PENDING_PREFIX}{source_id}:{request_id}"
        raw = await self._redis.get(key)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None

    async def _subscriber_loop(self):
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(PUBSUB_CHAN)
        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if not msg:
                await asyncio.sleep(0.05)
                continue
            try:
                payload = json.loads(msg["data"])
                target = payload.get("merchant_id", "")
                env = SignalEnvelope(**payload.get("env", {}))
            except Exception:
                continue

            if target == "*":
                for mid in list(self._local_conns.keys()):
                    ws = self._local_conns.get(mid)
                    if not ws:
                        continue
                    try:
                        await ws.send_text(env.model_dump_json())
                    except Exception:
                        await self.unregister(mid)
            else:
                ws = self._local_conns.get(target)
                if ws:
                    try:
                        await ws.send_text(env.model_dump_json())
                    except Exception:
                        await self.unregister(target)

    async def heartbeat_loop(self):
        while True:
            await asyncio.sleep(self.ping_interval)
            mids = list(self._local_conns.keys())
            dead = []
            for mid in mids:
                ws = self._local_conns.get(mid)
                if not ws:
                    continue
                try:
                    ping = SignalEnvelope(
                        msg_type=MsgType.HEARTBEAT,
                        sender_id="hub",
                        payload={"type": "ping", "ts": time.time()},
                    )
                    await ws.send_text(ping.model_dump_json())
                except Exception:
                    dead.append(mid)
                if time.time() - self._last_pong.get(mid, 0) > self.ping_interval + self.pong_timeout:
                    dead.append(mid)

            for mid in set(dead):
                await self.unregister(mid)
