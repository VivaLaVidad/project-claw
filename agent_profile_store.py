from __future__ import annotations

import json
import time
from typing import Any

try:
    import redis
except Exception:  # pragma: no cover
    redis = None


class AgentProfileStore:
    def __init__(self, redis_url: str = "", ttl_seconds: int = 86400):
        self._clients: dict[str, dict[str, Any]] = {}
        self._merchants: dict[str, dict[str, Any]] = {}
        self.ttl_seconds = ttl_seconds
        self._redis = None
        if redis_url and redis is not None:
            try:
                self._redis = redis.from_url(redis_url, decode_responses=True)
                self._redis.ping()
            except Exception:
                self._redis = None

    def upsert_client(self, client_id: str, profile: dict[str, Any]) -> dict[str, Any]:
        row = {"client_id": client_id, "profile": profile or {}, "updated_at": time.time()}
        if self._redis is not None:
            self._redis.setex(self._k("client", client_id), self.ttl_seconds, json.dumps(row, ensure_ascii=False))
            return row
        self._clients[client_id] = row
        return row

    def upsert_merchant(self, merchant_id: str, profile: dict[str, Any]) -> dict[str, Any]:
        row = {"merchant_id": merchant_id, "profile": profile or {}, "updated_at": time.time()}
        if self._redis is not None:
            self._redis.setex(self._k("merchant", merchant_id), self.ttl_seconds, json.dumps(row, ensure_ascii=False))
            return row
        self._merchants[merchant_id] = row
        return row

    def get_client(self, client_id: str) -> dict[str, Any]:
        if self._redis is not None:
            raw = self._redis.get(self._k("client", client_id))
            if raw:
                return (json.loads(raw) or {}).get("profile", {})
            return {}
        return (self._clients.get(client_id) or {}).get("profile", {})

    def get_merchant(self, merchant_id: str) -> dict[str, Any]:
        if self._redis is not None:
            raw = self._redis.get(self._k("merchant", merchant_id))
            if raw:
                return (json.loads(raw) or {}).get("profile", {})
            return {}
        return (self._merchants.get(merchant_id) or {}).get("profile", {})

    def _k(self, kind: str, id_: str) -> str:
        return f"claw:profile:{kind}:{id_}"
