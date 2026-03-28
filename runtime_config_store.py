"""
runtime_config_store.py - Project Claw v14.3
运行时配置存储（基于 RedisStore 基类重构）
"""
from __future__ import annotations

from typing import Any
from shared.redis_store import RedisStore


class RuntimeConfigStore(RedisStore):
    """
    运行时动态配置存储（如商家偏好、A2A 策略参数）。
    持久化到 Redis，内存降级时进程重启后丢失。

    用法：
        store = RuntimeConfigStore(redis_url=settings.REDIS_URL)
        store.save({"fee_rate": 0.01, "max_discount": 0.15})
        cfg = store.load()
    """

    def __init__(
        self,
        redis_url: str = "",
        key:       str = "preference",
    ) -> None:
        super().__init__(namespace="runtime", redis_url=redis_url, ttl_seconds=0)
        self._key = key

    def load(self) -> dict[str, Any]:
        """加载配置，不存在时返回空 dict。"""
        return self._get(self._key) or {}

    def save(self, data: dict[str, Any]) -> None:
        """保存配置（全量覆盖）。"""
        self._set(self._key, data or {}, ttl=0)

    def patch(self, updates: dict[str, Any]) -> dict[str, Any]:
        """局部更新配置（merge）。"""
        current = self.load()
        current.update(updates)
        self.save(current)
        return current

    def delete(self) -> None:
        """清除配置。"""
        self._delete(self._key)
