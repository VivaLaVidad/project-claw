"""
Project Claw 深度优化实现 - 第 1 部分：错误处理和连接池
文件位置：cloud_server/optimization_core.py
"""

import asyncio
import time
import uuid
from enum import Enum
from typing import Any, Dict, Optional
from datetime import datetime, timedelta

import asyncpg
import aioredis
from fastapi import HTTPException
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# 错误处理系统
# ═══════════════════════════════════════════════════════════════

class ErrorCode(str, Enum):
    """错误代码枚举"""
    SUCCESS = "0000"
    INVALID_REQUEST = "4001"
    UNAUTHORIZED = "4011"
    FORBIDDEN = "4031"
    NOT_FOUND = "4041"
    CONFLICT = "4091"
    RATE_LIMITED = "4291"
    INTERNAL_ERROR = "5001"
    SERVICE_UNAVAILABLE = "5031"
    TIMEOUT = "5041"


class ErrorResponse(BaseModel):
    """统一错误响应"""
    code: str
    message: str
    trace_id: str
    timestamp: float
    details: Optional[Dict[str, Any]] = None


class AppException(Exception):
    """应用异常基类"""
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        status_code: int = 500,
        details: Optional[Dict] = None
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        self.trace_id = str(uuid.uuid4())
        super().__init__(message)

    def to_response(self) -> ErrorResponse:
        """转换为响应对象"""
        return ErrorResponse(
            code=self.code.value,
            message=self.message,
            trace_id=self.trace_id,
            timestamp=time.time(),
            details=self.details
        )


class ValidationError(AppException):
    """验证错误"""
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(
            code=ErrorCode.INVALID_REQUEST,
            message=message,
            status_code=400,
            details=details
        )


class NotFoundError(AppException):
    """资源不存在错误"""
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(
            code=ErrorCode.NOT_FOUND,
            message=message,
            status_code=404,
            details=details
        )


class ConflictError(AppException):
    """冲突错误"""
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(
            code=ErrorCode.CONFLICT,
            message=message,
            status_code=409,
            details=details
        )


class RateLimitError(AppException):
    """速率限制错误"""
    def __init__(self, message: str = "请求过于频繁"):
        super().__init__(
            code=ErrorCode.RATE_LIMITED,
            message=message,
            status_code=429
        )


class TimeoutError(AppException):
    """超时错误"""
    def __init__(self, message: str = "请求超时"):
        super().__init__(
            code=ErrorCode.TIMEOUT,
            message=message,
            status_code=504
        )


# ═══════════════════════════════════════════════════════════════
# 连接池管理
# ═══════════════════════════════════════════════════════════════

class DatabasePool:
    """数据库连接池管理"""
    _pool: Optional[asyncpg.Pool] = None
    _lock = asyncio.Lock()

    @classmethod
    async def initialize(
        cls,
        dsn: str,
        min_size: int = 5,
        max_size: int = 20,
        command_timeout: int = 60
    ):
        """初始化连接池"""
        async with cls._lock:
            if cls._pool is None:
                cls._pool = await asyncpg.create_pool(
                    dsn,
                    min_size=min_size,
                    max_size=max_size,
                    command_timeout=command_timeout,
                    max_cached_statement_lifetime=300,
                    max_cacheable_statement_size=15000,
                )
                logger.info(f"数据库连接池已初始化 (min={min_size}, max={max_size})")

    @classmethod
    async def close(cls):
        """关闭连接池"""
        async with cls._lock:
            if cls._pool:
                await cls._pool.close()
                cls._pool = None
                logger.info("数据库连接池已关闭")

    @classmethod
    def get_pool(cls) -> asyncpg.Pool:
        """获取连接池"""
        if not cls._pool:
            raise RuntimeError("数据库连接池未初始化")
        return cls._pool

    @classmethod
    async def execute(cls, query: str, *args, **kwargs):
        """执行查询"""
        pool = cls.get_pool()
        async with pool.acquire() as conn:
            return await conn.execute(query, *args, **kwargs)

    @classmethod
    async def fetch(cls, query: str, *args, **kwargs):
        """获取多行"""
        pool = cls.get_pool()
        async with pool.acquire() as conn:
            return await conn.fetch(query, *args, **kwargs)

    @classmethod
    async def fetchrow(cls, query: str, *args, **kwargs):
        """获取单行"""
        pool = cls.get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchrow(query, *args, **kwargs)

    @classmethod
    async def fetchval(cls, query: str, *args, **kwargs):
        """获取单个值"""
        pool = cls.get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchval(query, *args, **kwargs)


# ═══════════════════════════════════════════════════════════════
# 缓存管理
# ═══════════════════════════════════════════════════════════════

class CacheManager:
    """缓存管理器"""
    _redis: Optional[aioredis.Redis] = None
    _lock = asyncio.Lock()

    @classmethod
    async def initialize(cls, redis_url: str):
        """初始化 Redis 连接"""
        async with cls._lock:
            if cls._redis is None:
                cls._redis = await aioredis.create_redis_pool(redis_url)
                logger.info("Redis 连接已初始化")

    @classmethod
    async def close(cls):
        """关闭 Redis 连接"""
        async with cls._lock:
            if cls._redis:
                cls._redis.close()
                await cls._redis.wait_closed()
                cls._redis = None
                logger.info("Redis 连接已关闭")

    @classmethod
    def get_redis(cls) -> aioredis.Redis:
        """获取 Redis 连接"""
        if not cls._redis:
            raise RuntimeError("Redis 连接未初始化")
        return cls._redis

    @classmethod
    async def get(cls, key: str) -> Optional[Any]:
        """获取缓存"""
        try:
            redis = cls.get_redis()
            value = await redis.get(key)
            if value:
                import json
                return json.loads(value)
            return None
        except Exception as e:
            logger.error(f"缓存获取失败: {key}, {e}")
            return None

    @classmethod
    async def set(cls, key: str, value: Any, ttl: int = 3600):
        """设置缓存"""
        try:
            redis = cls.get_redis()
            import json
            await redis.setex(
                key,
                ttl,
                json.dumps(value, default=str)
            )
        except Exception as e:
            logger.error(f"缓存设置失败: {key}, {e}")

    @classmethod
    async def delete(cls, key: str):
        """删除缓存"""
        try:
            redis = cls.get_redis()
            await redis.delete(key)
        except Exception as e:
            logger.error(f"缓存删除失败: {key}, {e}")

    @classmethod
    async def clear_pattern(cls, pattern: str):
        """清除匹配模式的缓存"""
        try:
            redis = cls.get_redis()
            keys = await redis.keys(pattern)
            if keys:
                await redis.delete(*keys)
        except Exception as e:
            logger.error(f"缓存清除失败: {pattern}, {e}")

    @classmethod
    def generate_key(cls, *parts: str) -> str:
        """生成缓存键"""
        import hashlib
        key = ":".join(parts)
        return hashlib.md5(key.encode()).hexdigest()


# ═══════════════════════════════════════════════════════════════
# 对话上下文管理
# ═══════════════════════════════════════════════════════════════

class DialogueContext:
    """对话上下文管理"""

    def __init__(self, session_id: str, max_history: int = 100):
        self.session_id = session_id
        self.max_history = max_history
        self.messages: list = []
        self.metadata: Dict = {}
        self.created_at = datetime.now()
        self.last_updated = datetime.now()

    def add_message(self, speaker: str, text: str, metadata: Dict = None):
        """添加消息"""
        message = {
            "speaker": speaker,
            "text": text,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        }
        self.messages.append(message)

        # 保持历史记录大小
        if len(self.messages) > self.max_history:
            self.messages = self.messages[-self.max_history:]

        self.last_updated = datetime.now()

    def get_recent_messages(self, count: int = 10) -> list:
        """获取最近的消息"""
        return self.messages[-count:]

    def get_context_summary(self) -> str:
        """获取上下文摘要"""
        recent = self.get_recent_messages(5)
        summary = "\n".join(
            f"{msg['speaker']}: {msg['text']}"
            for msg in recent
        )
        return summary

    def is_expired(self, ttl_minutes: int = 30) -> bool:
        """检查是否过期"""
        return (
            datetime.now() - self.last_updated
        ) > timedelta(minutes=ttl_minutes)

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "session_id": self.session_id,
            "messages": self.messages,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "last_updated": self.last_updated.isoformat()
        }
