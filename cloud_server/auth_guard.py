"""Project Claw 认证守卫 - cloud_server/auth_guard.py"""
import logging
import time
from typing import Optional, Dict
from functools import wraps
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class RateLimiter:
    """速率限制器"""
    
    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: Dict[str, list] = {}
    
    def is_allowed(self, client_id: str) -> bool:
        """检查是否允许请求"""
        now = time.time()
        
        if client_id not in self.requests:
            self.requests[client_id] = []
        
        # 清除过期的请求记录
        self.requests[client_id] = [
            req_time for req_time in self.requests[client_id]
            if now - req_time < self.window_seconds
        ]
        
        # 检查是否超过限制
        if len(self.requests[client_id]) >= self.max_requests:
            logger.warning(f"速率限制触发: {client_id}")
            return False
        
        # 记录新请求
        self.requests[client_id].append(now)
        return True

class AuthGuard:
    """认证守卫"""
    
    def __init__(self):
        self.rate_limiter = RateLimiter(max_requests=100, window_seconds=60)
        self.sessions: Dict[str, Dict] = {}
    
    def verify_rate_limit_only(self, client_id: str) -> bool:
        """仅验证速率限制"""
        return self.rate_limiter.is_allowed(client_id)
    
    def create_session(self, user_id: str, user_info: Dict) -> str:
        """创建会话"""
        import uuid
        session_id = str(uuid.uuid4())
        
        self.sessions[session_id] = {
            "user_id": user_id,
            "user_info": user_info,
            "created_at": datetime.now(),
            "last_activity": datetime.now()
        }
        
        logger.info(f"✓ 会话已创建: {session_id}")
        return session_id
    
    def verify_session(self, session_id: str) -> Optional[Dict]:
        """验证会话"""
        if session_id not in self.sessions:
            logger.warning(f"会话不存在: {session_id}")
            return None
        
        session = self.sessions[session_id]
        
        # 检查会话是否过期 (24 小时)
        if datetime.now() - session["created_at"] > timedelta(hours=24):
            logger.warning(f"会话已过期: {session_id}")
            del self.sessions[session_id]
            return None
        
        # 更新最后活动时间
        session["last_activity"] = datetime.now()
        
        return session
    
    def invalidate_session(self, session_id: str) -> bool:
        """使会话失效"""
        if session_id in self.sessions:
            del self.sessions[session_id]
            logger.info(f"✓ 会话已失效: {session_id}")
            return True
        return False

# 全局认证守卫实例
auth_guard = AuthGuard()

def verify_rate_limit_only(client_id: str) -> bool:
    """验证速率限制"""
    return auth_guard.verify_rate_limit_only(client_id)

def verify_session(session_id: str) -> Optional[Dict]:
    """验证会话"""
    return auth_guard.verify_session(session_id)

def create_session(user_id: str, user_info: Dict) -> str:
    """创建会话"""
    return auth_guard.create_session(user_id, user_info)

def invalidate_session(session_id: str) -> bool:
    """使会话失效"""
    return auth_guard.invalidate_session(session_id)
