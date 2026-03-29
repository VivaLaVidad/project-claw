"""
Project Claw 深度优化实现 - 第 2 部分：装饰器和性能监控
文件位置：cloud_server/optimization_decorators.py
"""

import asyncio
import time
from functools import wraps
from typing import Callable, Dict, Any
import logging

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# 装饰器
# ═══════════════════════════════════════════════════════════════

def with_error_handling(func: Callable) -> Callable:
    """错误处理装饰器"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        from .optimization_core import AppException, ErrorCode, TimeoutError as AppTimeoutError
        from fastapi import HTTPException
        
        try:
            return await func(*args, **kwargs)
        except AppException as e:
            logger.error(f"应用异常: {e.trace_id}, {e.message}")
            raise HTTPException(
                status_code=e.status_code,
                detail=e.to_response().dict()
            )
        except asyncio.TimeoutError:
            logger.error("请求超时")
            error = AppTimeoutError()
            raise HTTPException(
                status_code=504,
                detail=error.to_response().dict()
            )
        except Exception as e:
            logger.error(f"未知异常: {e}", exc_info=True)
            error = AppException(
                code=ErrorCode.INTERNAL_ERROR,
                message="内部服务器错误",
                status_code=500
            )
            raise HTTPException(
                status_code=500,
                detail=error.to_response().dict()
            )
    return wrapper


def with_timeout(seconds: int = 30) -> Callable:
    """超时装饰器"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            from .optimization_core import TimeoutError as AppTimeoutError
            
            try:
                return await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=seconds
                )
            except asyncio.TimeoutError:
                logger.error(f"函数超时: {func.__name__}")
                raise AppTimeoutError(f"{func.__name__} 执行超时")
        return wrapper
    return decorator


def with_cache(ttl: int = 3600) -> Callable:
    """缓存装饰器"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            from .optimization_core import CacheManager
            
            # 生成缓存键
            cache_key = CacheManager.generate_key(
                func.__name__,
                str(args),
                str(kwargs)
            )

            # 尝试从缓存获取
            cached = await CacheManager.get(cache_key)
            if cached is not None:
                logger.debug(f"缓存命中: {cache_key}")
                return cached

            # 执行函数
            result = await func(*args, **kwargs)

            # 保存到缓存
            await CacheManager.set(cache_key, result, ttl)

            return result
        return wrapper
    return decorator


def with_retry(max_attempts: int = 3, delay: float = 1.0) -> Callable:
    """重试装饰器"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        logger.warning(
                            f"函数执行失败 (尝试 {attempt + 1}/{max_attempts}): "
                            f"{func.__name__}, 错误: {e}"
                        )
                        await asyncio.sleep(delay * (2 ** attempt))  # 指数退避
                    else:
                        logger.error(
                            f"函数执行失败 (所有尝试都失败): {func.__name__}"
                        )
            
            raise last_exception
        return wrapper
    return decorator


def with_performance_monitor(func: Callable) -> Callable:
    """性能监控装饰器"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        from .optimization_decorators import PerformanceMonitor
        
        start_time = time.time()
        try:
            result = await func(*args, **kwargs)
            duration = time.time() - start_time
            PerformanceMonitor.record(func.__name__, duration, "success")
            return result
        except Exception as e:
            duration = time.time() - start_time
            PerformanceMonitor.record(func.__name__, duration, "error")
            raise
    return wrapper


# ═══════════════════════════════════════════════════════════════
# 性能监控
# ═══════════════════════════════════════════════════════════════

class PerformanceMonitor:
    """性能监控"""
    _metrics: Dict[str, list] = {}

    @classmethod
    def record(cls, name: str, duration: float, status: str = "success"):
        """记录性能指标"""
        if name not in cls._metrics:
            cls._metrics[name] = []

        cls._metrics[name].append({
            "duration": duration,
            "status": status,
            "timestamp": time.time()
        })

        # 只保留最近 1000 条记录
        if len(cls._metrics[name]) > 1000:
            cls._metrics[name] = cls._metrics[name][-1000:]

    @classmethod
    def get_stats(cls, name: str) -> Dict:
        """获取统计信息"""
        if name not in cls._metrics:
            return {}

        metrics = cls._metrics[name]
        durations = [m["duration"] for m in metrics]

        if not durations:
            return {}

        sorted_durations = sorted(durations)
        return {
            "count": len(metrics),
            "avg": sum(durations) / len(durations),
            "min": min(durations),
            "max": max(durations),
            "p50": sorted_durations[int(len(durations) * 0.50)],
            "p95": sorted_durations[int(len(durations) * 0.95)],
            "p99": sorted_durations[int(len(durations) * 0.99)]
        }

    @classmethod
    def get_all_stats(cls) -> Dict:
        """获取所有统计信息"""
        return {name: cls.get_stats(name) for name in cls._metrics}

    @classmethod
    def reset(cls):
        """重置所有指标"""
        cls._metrics.clear()


# ═══════════════════════════════════════════════════════════════
# 请求签名验证
# ═══════════════════════════════════════════════════════════════

class RequestSigner:
    """请求签名验证"""

    def __init__(self, secret_key: str):
        self.secret_key = secret_key

    def sign(self, data: Dict[str, Any], timestamp: int = None) -> str:
        """生成签名"""
        import hmac
        import hashlib

        if timestamp is None:
            timestamp = int(time.time())

        # 排序数据
        sorted_data = sorted(data.items())
        message = f"{timestamp}:" + "&".join(
            f"{k}={v}" for k, v in sorted_data
        )

        # 生成签名
        signature = hmac.new(
            self.secret_key.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()

        return signature

    def verify(self, data: Dict[str, Any], signature: str, timestamp: int) -> bool:
        """验证签名"""
        import hmac

        # 检查时间戳（防重放攻击）
        if abs(int(time.time()) - timestamp) > 300:  # 5分钟
            logger.warning(f"时间戳过期: {timestamp}")
            return False

        # 验证签名
        expected_signature = self.sign(data, timestamp)
        return hmac.compare_digest(signature, expected_signature)


# ═══════════════════════════════════════════════════════════════
# 速率限制
# ═══════════════════════════════════════════════════════════════

class RateLimiter:
    """速率限制器"""
    _limits: Dict[str, list] = {}

    @classmethod
    def is_allowed(cls, key: str, max_requests: int = 100, window: int = 60) -> bool:
        """检查是否允许请求"""
        now = time.time()
        
        if key not in cls._limits:
            cls._limits[key] = []
        
        # 清除过期的请求记录
        cls._limits[key] = [
            t for t in cls._limits[key]
            if now - t < window
        ]
        
        # 检查是否超过限制
        if len(cls._limits[key]) >= max_requests:
            return False
        
        # 记录新请求
        cls._limits[key].append(now)
        return True

    @classmethod
    def get_remaining(cls, key: str, max_requests: int = 100, window: int = 60) -> int:
        """获取剩余请求数"""
        now = time.time()
        
        if key not in cls._limits:
            return max_requests
        
        # 清除过期的请求记录
        cls._limits[key] = [
            t for t in cls._limits[key]
            if now - t < window
        ]
        
        return max(0, max_requests - len(cls._limits[key]))

    @classmethod
    def reset(cls, key: str = None):
        """重置限制"""
        if key:
            cls._limits.pop(key, None)
        else:
            cls._limits.clear()
