from __future__ import annotations

import json
import time
from typing import Any

try:
    import redis
except Exception:  # pragma: no cover
    redis = None


class IdempotencyStore:
    def __init__(self, redis_url: str = "", ttl_seconds: int = 300):
        self.ttl_seconds = ttl_seconds
        self._mem: dict[str, tuple[float, dict[str, Any]]] = {}
        self._redis = None
        if redis_url and redis is not None:
            try:
                self._redis = redis.from_url(redis_url, decode_responses=True)
                self._redis.ping()
            except Exception:
                self._redis = None

    def get(self, key: str) -> dict[str, Any] | None:
        if not key:
            return None
        if self._redis is not None:
            raw = self._redis.get(self._k(key))
            return json.loads(raw) if raw else None
        self._cleanup_mem()
        entry = self._mem.get(key)
        return entry[1] if entry else None

    def set(self, key: str, value: dict[str, Any]) -> None:
        if not key:
            return
        if self._redis is not None:
            self._redis.setex(self._k(key), self.ttl_seconds, json.dumps(value, ensure_ascii=False))
            return
        self._cleanup_mem()
        self._mem[key] = (time.time(), value)

    def _k(self, key: str) -> str:
        return f"claw:idempotency:{key}"

    def _cleanup_mem(self) -> None:
        now = time.time()
        expired = [k for k, (ts, _) in self._mem.items() if now - ts > self.ttl_seconds]
        for k in expired:
            self._mem.pop(k, None)
