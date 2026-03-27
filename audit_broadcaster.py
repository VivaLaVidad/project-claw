"""审计事件广播器 - 驱动上帝视角大屏实时数据"""
import asyncio
import time
from typing import List


class AuditBroadcaster:
    """将所有 A2A 事件实时推送给所有监控连接（上帝视角大屏）。"""

    def __init__(self):
        self._clients: List[asyncio.Queue] = []
        self._lock = None
        self.total_negotiations: int = 0
        self.total_savings: float = 0.0
        self.trade_log: List[dict] = []

    def init_lock(self):
        """在事件循环中初始化锁"""
        self._lock = asyncio.Lock()

    async def subscribe(self) -> asyncio.Queue:
        """订阅审计流"""
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        if self._lock:
            async with self._lock:
                self._clients.append(q)
        else:
            self._clients.append(q)
        return q

    async def unsubscribe(self, q: asyncio.Queue) -> None:
        """取消订阅"""
        if self._lock:
            async with self._lock:
                try:
                    self._clients.remove(q)
                except ValueError:
                    pass
        else:
            try:
                self._clients.remove(q)
            except ValueError:
                pass

    async def emit(self, event: dict) -> None:
        """向所有监控客户端广播事件"""
        event.setdefault("ts", time.time())
        if not self._lock:
            return
        async with self._lock:
            dead = []
            for q in self._clients:
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    dead.append(q)
            for q in dead:
                try:
                    self._clients.remove(q)
                except ValueError:
                    pass

    def record_trade(self, merchant_id: str, item: str,
                     normal_price: float, final_price: float,
                     tags: list) -> None:
        """记录成交"""
        savings = max(0.0, normal_price - final_price)
        self.total_negotiations += 1
        self.total_savings += savings
        self.trade_log.append({
            "ts": time.time(),
            "merchant_id": merchant_id,
            "item": item,
            "normal_price": normal_price,
            "final_price": final_price,
            "savings": round(savings, 2),
            "tags": tags,
        })
        if len(self.trade_log) > 500:
            self.trade_log = self.trade_log[-500:]

    def snapshot(self, online_merchants: int = 0) -> dict:
        """获取当前快照"""
        return {
            "online_merchants": online_merchants,
            "total_negotiations": self.total_negotiations,
            "total_savings": round(self.total_savings, 2),
            "recent_trades": self.trade_log[-20:],
            "audit_subscribers": len(self._clients),
        }
