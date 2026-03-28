"""
shared/redis_store.py - Project Claw v14.3
统一 RedisStore 抽象基类

所有需要 Redis/内存双模式存储的组件继承此基类：
- AgentProfileStore
- IdempotencyStore
- RuntimeConfigStore

特性：
- Redis 连接失败自动降级到内存
- 统一 key 命名空间：claw:{namespace}:{key}
- 惰性内存 TTL 清理
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

logger = logging.getLogger("claw.store")

try:
    import redis as _redis_lib
    _REDIS_AVAILABLE = True
except ImportError:
    _redis_lib = None  # type: ignore
    _REDIS_AVAILABLE = False


class RedisStore:
    """
    Redis/内存双模式 KV 存储基类。
    子类只需调用 _get / _set / _delete，无需关心底层。
    """

    def __init__(
        self,
        namespace:   str,
        redis_url:   str = "",
        ttl_seconds: int = 300,
    ) -> None:
        self._ns          = namespace
        self._ttl         = ttl_seconds
        self._mem:        dict[str, tuple[float, Any]] = {}
        self._redis:      Any = None
        self._use_redis   = False

        if redis_url and _REDIS_AVAILABLE:
            try:
                r = _redis_lib.from_url(redis_url, decode_responses=True)
                r.ping()
                self._redis    = r
                self._use_redis = True
                logger.info(f"[{self.__class__.__name__}] Redis 已连接: {redis_url[:30]}...")
            except Exception as e:
                logger.warning(f"[{self.__class__.__name__}] Redis 连接失败，降级到内存: {e}")

    # ── 内部操作（子类使用）──────────────────────────────────
    def _k(self, key: str) -> str:
        return f"claw:{self._ns}:{key}"

    def _get(self, key: str) -> Optional[Any]:
        if self._use_redis:
            raw = self._redis.get(self._k(key))
            return json.loads(raw) if raw else None
        self._cleanup()
        entry = self._mem.get(key)
        return entry[1] if entry else None

    def _set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        effective_ttl = ttl if ttl is not None else self._ttl
        if self._use_redis:
            if effective_ttl > 0:
                self._redis.setex(self._k(key), effective_ttl, json.dumps(value, ensure_ascii=False))
            else:
                self._redis.set(self._k(key), json.dumps(value, ensure_ascii=False))
            return
        self._cleanup()
        self._mem[key] = (time.time(), value)

    def _delete(self, key: str) -> None:
        if self._use_redis:
            self._redis.delete(self._k(key))
        else:
            self._mem.pop(key, None)

    def _cleanup(self) -> None:
        """惰性清理过期内存条目。"""
        if not self._ttl:
            return
        now     = time.time()
        expired = [k for k, (ts, _) in self._mem.items() if now - ts > self._ttl]
        for k in expired:
            del self._mem[k]

    @property
    def backend(self) -> str:
        return "redis" if self._use_redis else "memory"
