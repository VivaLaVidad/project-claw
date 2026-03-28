"""
agent_profile_store.py - Project Claw v14.3
Agent 画像存储（基于 RedisStore 基类重构）
"""
from __future__ import annotations

import time
from typing import Any
from shared.redis_store import RedisStore


class AgentProfileStore(RedisStore):
    """
    C/B 端 Agent 画像存储。
    支持 Redis（生产）/ 内存（开发/CI）双模式。

    用法：
        store = AgentProfileStore(redis_url=settings.REDIS_URL)
        store.upsert_client("c-001", {"budget_max": 30.0})
        profile = store.get_client("c-001")
    """

    def __init__(self, redis_url: str = "", ttl_seconds: int = 86400) -> None:
        super().__init__(namespace="profile", redis_url=redis_url, ttl_seconds=ttl_seconds)

    # ── C 端 ────────────────────────────────────────────────
    def upsert_client(self, client_id: str, profile: dict[str, Any]) -> dict[str, Any]:
        row = {"client_id": client_id, "profile": profile or {}, "updated_at": time.time()}
        self._set(f"client:{client_id}", row)
        return row

    def get_client(self, client_id: str) -> dict[str, Any]:
        row = self._get(f"client:{client_id}")
        return (row or {}).get("profile", {})

    def delete_client(self, client_id: str) -> None:
        self._delete(f"client:{client_id}")

    # ── B 端 ────────────────────────────────────────────────
    def upsert_merchant(self, merchant_id: str, profile: dict[str, Any]) -> dict[str, Any]:
        row = {"merchant_id": merchant_id, "profile": profile or {}, "updated_at": time.time()}
        self._set(f"merchant:{merchant_id}", row)
        return row

    def get_merchant(self, merchant_id: str) -> dict[str, Any]:
        row = self._get(f"merchant:{merchant_id}")
        return (row or {}).get("profile", {})

    def delete_merchant(self, merchant_id: str) -> None:
        self._delete(f"merchant:{merchant_id}")
