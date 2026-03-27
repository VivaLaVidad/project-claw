from __future__ import annotations

import json
from typing import Any

try:
    import redis
except Exception:  # pragma: no cover
    redis = None


class RuntimeConfigStore:
    def __init__(self, redis_url: str = "", key: str = "claw:runtime:preference"):
        self.key = key
        self._mem: dict[str, Any] = {}
        self._redis = None
        if redis_url and redis is not None:
            try:
                self._redis = redis.from_url(redis_url, decode_responses=True)
                self._redis.ping()
            except Exception:
                self._redis = None

    def load(self) -> dict[str, Any]:
        if self._redis is not None:
            raw = self._redis.get(self.key)
            return json.loads(raw) if raw else {}
        return dict(self._mem)

    def save(self, data: dict[str, Any]) -> None:
        payload = data or {}
        if self._redis is not None:
            self._redis.set(self.key, json.dumps(payload, ensure_ascii=False))
            return
        self._mem = dict(payload)
