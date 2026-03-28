"""
idempotency_store.py - Project Claw v14.3
幂等存储（基于 RedisStore 基类重构）
"""
from __future__ import annotations

from typing import Any, Optional
from shared.redis_store import RedisStore


class IdempotencyStore(RedisStore):
    """
    幂等键值存储。
    同一 idempotency_key 在 TTL 内只处理一次。

    用法：
        store = IdempotencyStore(redis_url=settings.REDIS_URL)
        if store.get(key):       # 已处理过
            return cached_result
        result = do_work()
        store.set(key, result)   # 缓存结果
    """

    def __init__(self, redis_url: str = "", ttl_seconds: int = 300) -> None:
        super().__init__(namespace="idempotency", redis_url=redis_url, ttl_seconds=ttl_seconds)

    def get(self, key: str) -> Optional[dict[str, Any]]:
        if not key:
            return None
        return self._get(key)

    def set(self, key: str, value: dict[str, Any]) -> None:
        if not key:
            return
        self._set(key, value)

    def delete(self, key: str) -> None:
        self._delete(key)
