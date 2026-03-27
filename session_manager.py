"""
Project Claw v13.0 - session_manager.py
多轮对话上下文管理器

功能：
  - 每个用户独立会话历史（最近 N 轮）
  - 自动过期清理（LRU + TTL）
  - 线程安全
  - 支持导出为 LLM messages 格式
"""
from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import List, Optional, Dict

logger = logging.getLogger("claw.session")


@dataclass
class Turn:
    """单轮对话"""
    user_msg:  str
    bot_reply: str
    timestamp: float = field(default_factory=time.time)
    intent:    str   = "chat"
    latency_ms: float = 0.0


class Session:
    """单用户会话"""

    def __init__(
        self,
        user_id:   str,
        max_turns: int   = 10,
        ttl_sec:   int   = 1800,   # 30 分钟无活动则过期
    ):
        self.user_id    = user_id
        self.max_turns  = max_turns
        self.ttl_sec    = ttl_sec
        self.turns:     List[Turn] = []
        self.created_at = time.time()
        self.updated_at = time.time()
        self._lock      = threading.Lock()

    def add(self, user_msg: str, bot_reply: str, intent: str = "chat", latency_ms: float = 0.0):
        with self._lock:
            self.turns.append(Turn(
                user_msg=user_msg,
                bot_reply=bot_reply,
                intent=intent,
                latency_ms=latency_ms,
            ))
            if len(self.turns) > self.max_turns:
                self.turns.pop(0)
            self.updated_at = time.time()

    def is_expired(self) -> bool:
        return time.time() - self.updated_at > self.ttl_sec

    def to_messages(self, system_prompt: str = "") -> List[dict]:
        """导出为 OpenAI / DeepSeek messages 格式"""
        msgs = []
        if system_prompt:
            msgs.append({"role": "system", "content": system_prompt})
        with self._lock:
            for t in self.turns[-6:]:   # 最近 6 轮作为上下文
                msgs.append({"role": "user",      "content": t.user_msg})
                msgs.append({"role": "assistant", "content": t.bot_reply})
        return msgs

    def last_intent(self) -> str:
        with self._lock:
            return self.turns[-1].intent if self.turns else "chat"

    def summary(self) -> dict:
        with self._lock:
            return {
                "user_id":    self.user_id,
                "turns":      len(self.turns),
                "created_at": self.created_at,
                "updated_at": self.updated_at,
                "last_intent": self.last_intent(),
            }


class SessionManager:
    """
    全局会话管理器（LRU + TTL）

    用法：
        mgr = SessionManager()
        sess = mgr.get_or_create(user_id)
        sess.add(user_msg, bot_reply)
        msgs = sess.to_messages(system_prompt)
    """

    def __init__(
        self,
        max_sessions: int = 500,
        max_turns:    int = 10,
        ttl_sec:      int = 1800,
        gc_interval:  int = 300,
    ):
        self.max_sessions = max_sessions
        self.max_turns    = max_turns
        self.ttl_sec      = ttl_sec
        self._sessions: OrderedDict[str, Session] = OrderedDict()
        self._lock = threading.Lock()

        # 后台 GC 线程
        self._gc_thread = threading.Thread(
            target=self._gc_loop,
            args=(gc_interval,),
            daemon=True,
            name="SessionGC",
        )
        self._gc_thread.start()
        logger.info(f"[SessionManager] 初始化完成 max={max_sessions} ttl={ttl_sec}s")

    def get_or_create(self, user_id: str) -> Session:
        with self._lock:
            if user_id in self._sessions:
                self._sessions.move_to_end(user_id)   # LRU 更新
                return self._sessions[user_id]
            # 新建
            if len(self._sessions) >= self.max_sessions:
                evicted = next(iter(self._sessions))
                del self._sessions[evicted]
                logger.debug(f"[SessionManager] 淘汰会话 {evicted}")
            sess = Session(user_id, self.max_turns, self.ttl_sec)
            self._sessions[user_id] = sess
            logger.debug(f"[SessionManager] 新建会话 {user_id}")
            return sess

    def get(self, user_id: str) -> Optional[Session]:
        with self._lock:
            return self._sessions.get(user_id)

    def delete(self, user_id: str):
        with self._lock:
            self._sessions.pop(user_id, None)

    def stats(self) -> dict:
        with self._lock:
            sessions = list(self._sessions.values())
        return {
            "total":   len(sessions),
            "active":  sum(1 for s in sessions if not s.is_expired()),
            "expired": sum(1 for s in sessions if s.is_expired()),
        }

    def _gc_loop(self, interval: int):
        while True:
            time.sleep(interval)
            try:
                self._gc()
            except Exception as e:
                logger.error(f"[SessionManager] GC 失败: {e}")

    def _gc(self):
        with self._lock:
            expired = [uid for uid, s in self._sessions.items() if s.is_expired()]
            for uid in expired:
                del self._sessions[uid]
        if expired:
            logger.info(f"[SessionManager] GC 清理 {len(expired)} 个过期会话")


# 全局单例
_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    global _manager
    if _manager is None:
        _manager = SessionManager()
    return _manager
