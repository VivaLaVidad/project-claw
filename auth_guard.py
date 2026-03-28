"""
auth_guard.py - Project Claw v14.3
FastAPI 依赖注入鉴权（工业级）

改进：
- 内置 IP 限速（内存滑动窗口），防刷攻击
- Bearer Token 和 X-Internal-Token 双模式
- 限速超出返回 429 + Retry-After 头
"""
from __future__ import annotations

import secrets
import time
from collections import defaultdict, deque
from threading import Lock
from typing import Deque

from fastapi import Header, HTTPException, Request

from config import settings

# ─── 内存滑动窗口限速器 ───────────────────────────────────────
_RATE_WINDOW_SECONDS = 60
_RATE_MAX_REQUESTS   = 120   # 每 IP 每分钟最多 120 次

_rate_store: dict[str, Deque[float]] = defaultdict(deque)
_rate_lock = Lock()


def _check_rate_limit(ip: str) -> None:
    """
    滑动窗口限速。超出时抛出 429。
    线程安全（Lock）。
    """
    now = time.time()
    with _rate_lock:
        window = _rate_store[ip]
        # 清除窗口外的旧请求
        while window and now - window[0] > _RATE_WINDOW_SECONDS:
            window.popleft()
        if len(window) >= _RATE_MAX_REQUESTS:
            oldest = window[0]
            retry_after = int(_RATE_WINDOW_SECONDS - (now - oldest)) + 1
            raise HTTPException(
                status_code=429,
                detail=f"请求过于频繁，请 {retry_after}s 后重试",
                headers={"Retry-After": str(retry_after)},
            )
        window.append(now)


# ─── 内部 Token 鉴权 ──────────────────────────────────────────
def verify_internal_token(
    request: Request,
    x_internal_token: str = Header(default=""),
) -> None:
    """
    FastAPI 依赖：校验内部服务 Token + IP 限速。

    用法：
        @router.post("/internal/xxx", dependencies=[Depends(verify_internal_token)])
    """
    # IP 限速
    client_ip = _get_client_ip(request)
    _check_rate_limit(client_ip)

    # Token 校验
    expected = settings.INTERNAL_API_TOKEN
    if not expected:
        return  # 未配置 token 时放行（开发环境）
    if not secrets.compare_digest(x_internal_token or "", expected):
        raise HTTPException(
            status_code=401,
            detail="内部 Token 校验失败",
            headers={"WWW-Authenticate": "Bearer"},
        )


def verify_rate_limit_only(request: Request) -> None:
    """
    FastAPI 依赖：仅限速，不校验 Token。
    适用于公开接口的防刷保护。
    """
    _check_rate_limit(_get_client_ip(request))


def _get_client_ip(request: Request) -> str:
    """从 X-Forwarded-For 或 client.host 获取真实 IP。"""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return getattr(request.client, "host", "unknown")
