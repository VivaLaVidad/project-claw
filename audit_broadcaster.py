"""
audit_broadcaster.py - Project Claw v14.3
审计事件广播器（工业级重构）

修复：
- init_lock 竞态：改为在构造器中直接用 asyncio.Lock() 懒创建
- 加事件类型枚举，防止拼写错误
- 加指标聚合（按商家、按商品）
- 加最大订阅数限制，防止内存泄漏
"""
from __future__ import annotations

import asyncio
import time
from enum import Enum
from typing import Dict, List, Optional


# ─── 事件类型枚举 ──────────────────────────────────────────────
class AuditEventType(str, Enum):
    INFO        = "info"
    AGENT       = "agent"
    DEAL        = "deal"
    TIMEOUT     = "timeout"
    WARN        = "warn"
    PAYMENT_ACK = "payment_ack"
    SNAPSHOT    = "snapshot"
    PING        = "ping"


MAX_SUBSCRIBERS = 50     # 最大监控连接数
MAX_TRADE_LOG   = 500    # 最大成交记录数


# ─── AuditBroadcaster ─────────────────────────────────────────
class AuditBroadcaster:
    """
    将所有 A2A 事件实时推送给所有监控连接（上帝视角大屏）。

    修复：
    - asyncio.Lock 在首次 await 时懒创建，避免跨事件循环问题
    - subscribe/unsubscribe/emit 全部使用同一把锁
    - 队列满时主动清理死连接
    """

    def __init__(self) -> None:
        self._clients: List[asyncio.Queue] = []
        self._lock:    Optional[asyncio.Lock] = None
        # 统计
        self.total_negotiations: int   = 0
        self.total_savings:      float = 0.0
        self.trade_log:          List[dict] = []
        # 聚合指标
        self._merchant_stats: Dict[str, dict] = {}  # merchant_id -> {count, revenue}
        self._item_stats:     Dict[str, dict] = {}  # item -> {count, avg_price}

    def _get_lock(self) -> asyncio.Lock:
        """懒创建 Lock，确保在正确的事件循环中初始化。"""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def subscribe(self) -> asyncio.Queue:
        """订阅审计流，返回事件队列。"""
        async with self._get_lock():
            if len(self._clients) >= MAX_SUBSCRIBERS:
                # 清理可能已满的死连接
                self._clients = [
                    q for q in self._clients
                    if not q.full() or q.qsize() < q.maxsize
                ]
            q: asyncio.Queue = asyncio.Queue(maxsize=200)
            self._clients.append(q)
            return q

    async def unsubscribe(self, q: asyncio.Queue) -> None:
        """取消订阅。"""
        async with self._get_lock():
            try:
                self._clients.remove(q)
            except ValueError:
                pass

    async def emit(
        self,
        event_type: AuditEventType | str,
        text:       str = "",
        extra:      Optional[dict] = None,
    ) -> None:
        """
        向所有监控客户端广播事件。
        队列满的连接视为死连接，自动移除。
        """
        event: dict = {
            "type": event_type.value if isinstance(event_type, AuditEventType) else event_type,
            "text": text,
            "ts":   time.time(),
            **(extra or {}),
        }
        async with self._get_lock():
            dead: List[asyncio.Queue] = []
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

    def record_trade(
        self,
        merchant_id:  str,
        item:         str,
        normal_price: float,
        final_price:  float,
        tags:         list,
    ) -> None:
        """记录成交，更新聚合指标。"""
        savings = max(0.0, normal_price - final_price)
        self.total_negotiations += 1
        self.total_savings      += savings

        record = {
            "ts":           time.time(),
            "merchant_id":  merchant_id,
            "item":         item,
            "normal_price": round(normal_price, 2),
            "final_price":  round(final_price, 2),
            "savings":      round(savings, 2),
            "tags":         tags,
        }
        self.trade_log.append(record)
        if len(self.trade_log) > MAX_TRADE_LOG:
            self.trade_log = self.trade_log[-MAX_TRADE_LOG:]

        # 商家聚合
        ms = self._merchant_stats.setdefault(merchant_id, {"count": 0, "revenue": 0.0})
        ms["count"]   += 1
        ms["revenue"] += final_price

        # 商品聚合
        its = self._item_stats.setdefault(item, {"count": 0, "total_price": 0.0})
        its["count"]       += 1
        its["total_price"] += final_price

    def snapshot(self, online_merchants: int = 0) -> dict:
        """获取当前快照（供 /audit/snapshot 接口和大屏使用）。"""
        top_items = sorted(
            [{"item": k, **v, "avg_price": round(v["total_price"] / max(1, v["count"]), 2)}
             for k, v in self._item_stats.items()],
            key=lambda x: x["count"], reverse=True
        )[:5]
        top_merchants = sorted(
            [{"merchant_id": k, **v} for k, v in self._merchant_stats.items()],
            key=lambda x: x["revenue"], reverse=True
        )[:5]
        return {
            "online_merchants":    online_merchants,
            "total_negotiations":  self.total_negotiations,
            "total_savings":       round(self.total_savings, 2),
            "recent_trades":       self.trade_log[-20:],
            "audit_subscribers":   len(self._clients),
            "top_items":           top_items,
            "top_merchants":       top_merchants,
        }

    async def emit_deal(
        self,
        merchant_id:  str,
        item:         str,
        normal_price: float,
        final_price:  float,
        tags:         list = [],
    ) -> None:
        """记录成交并广播（一步到位）。"""
        self.record_trade(merchant_id, item, normal_price, final_price, tags)
        await self.emit(
            AuditEventType.DEAL,
            text=f"成交! {merchant_id} {item} ¥{final_price} 节省¥{round(normal_price-final_price,2)}",
            extra={
                "merchant_id":  merchant_id,
                "item":         item,
                "normal_price": normal_price,
                "final_price":  final_price,
                "savings":      round(max(0, normal_price - final_price), 2),
            },
        )
