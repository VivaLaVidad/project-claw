from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime
from typing import Optional

from sqlalchemy import and_, desc, func, select

from cloud_server.data_models import ClientORM, MerchantORM, TradeLedgerORM, TradeStatusEnum
from cloud_server.db import session_scope
from shared.claw_protocol import TradeRequest


def _audit_hash(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class ClientRepository:
    async def upsert_basic(self, client_id: str):
        async with session_scope() as s:
            obj = await s.get(ClientORM, client_id)
            if obj is None:
                obj = ClientORM(client_id=client_id)
                s.add(obj)
            obj.updated_at = time.time()


class MerchantRepository:
    async def upsert_basic(self, merchant_id: str, promoter_id: str = ""):
        async with session_scope() as s:
            obj = await s.get(MerchantORM, merchant_id)
            if obj is None:
                obj = MerchantORM(merchant_id=merchant_id, promoter_id=promoter_id)
                s.add(obj)
            else:
                if promoter_id:
                    obj.promoter_id = promoter_id
                obj.updated_at = time.time()


class TradeLedgerRepository:
    async def create_request(self, req: TradeRequest):
        async with session_scope() as s:
            existing = await s.scalar(select(TradeLedgerORM).where(TradeLedgerORM.request_id == req.request_id))
            if existing:
                return
            payload = {
                "request_id": req.request_id,
                "client_id": req.client_id,
                "item_name": req.item_name,
                "demand_text": req.demand_text,
                "max_price": req.max_price,
                "quantity": req.quantity,
                "timeout_sec": req.timeout_sec,
            }
            row = TradeLedgerORM(
                trade_id=req.request_id,
                request_id=req.request_id,
                client_id=req.client_id,
                item_name=req.item_name,
                demand_text=req.demand_text,
                max_price=req.max_price,
                quantity=req.quantity,
                timeout_sec=req.timeout_sec,
                original_price=req.max_price,
                final_price=0,
                status=TradeStatusEnum.pending,
                audit_hash=_audit_hash(payload),
                created_at=time.time(),
                updated_at=time.time(),
            )
            s.add(row)

    async def mark_executed(self, request_id: str, merchant_id: str, offer_id: str, final_price: float):
        async with session_scope() as s:
            row = await s.scalar(select(TradeLedgerORM).where(TradeLedgerORM.request_id == request_id))
            if not row:
                return
            payload = {
                "request_id": request_id,
                "merchant_id": merchant_id,
                "offer_id": offer_id,
                "final_price": final_price,
                "status": "executed",
            }
            row.merchant_id = merchant_id
            row.offer_id = offer_id
            row.final_price = final_price
            row.status = TradeStatusEnum.executed
            row.executed_at = time.time()
            row.updated_at = time.time()
            row.audit_hash = _audit_hash(payload)

    async def mark_failed(self, request_id: str, reason: str):
        async with session_scope() as s:
            row = await s.scalar(select(TradeLedgerORM).where(TradeLedgerORM.request_id == request_id))
            if not row:
                return
            payload = {
                "request_id": request_id,
                "status": "failed",
                "reason": reason,
            }
            row.status = TradeStatusEnum.failed
            row.error_reason = reason
            row.updated_at = time.time()
            row.audit_hash = _audit_hash(payload)

    async def by_client(self, client_id: str, limit: int = 20):
        async with session_scope() as s:
            rows = await s.scalars(
                select(TradeLedgerORM)
                .where(TradeLedgerORM.client_id == client_id)
                .order_by(desc(TradeLedgerORM.created_at))
                .limit(limit)
            )
            return [self._to_dict(x) for x in rows.all()]

    async def by_merchant(self, merchant_id: str, limit: int = 50, status: Optional[str] = None):
        async with session_scope() as s:
            filters = [TradeLedgerORM.merchant_id == merchant_id]
            if status:
                filters.append(TradeLedgerORM.status == TradeStatusEnum(status))
            rows = await s.scalars(
                select(TradeLedgerORM)
                .where(and_(*filters))
                .order_by(desc(TradeLedgerORM.created_at))
                .limit(limit)
            )
            return [self._to_dict(x) for x in rows.all()]

    async def merchant_today_summary(self, merchant_id: str):
        day_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        async with session_scope() as s:
            row = await s.execute(
                select(
                    func.count(TradeLedgerORM.trade_id),
                    func.coalesce(func.sum(TradeLedgerORM.final_price), 0.0),
                ).where(
                    TradeLedgerORM.merchant_id == merchant_id,
                    TradeLedgerORM.status == TradeStatusEnum.executed,
                    TradeLedgerORM.executed_at >= day_start,
                )
            )
            cnt, revenue = row.one()
            return {"today_order_count": int(cnt or 0), "today_revenue": float(revenue or 0)}

    async def merchant_pending_count(self, merchant_id: str):
        async with session_scope() as s:
            row = await s.execute(
                select(func.count(TradeLedgerORM.trade_id)).where(
                    TradeLedgerORM.merchant_id == merchant_id,
                    TradeLedgerORM.status.in_([TradeStatusEnum.pending, TradeStatusEnum.accepted]),
                )
            )
            return int(row.scalar() or 0)

    @staticmethod
    def _to_dict(row: TradeLedgerORM):
        return {
            "request_id": row.request_id,
            "trade_id": row.trade_id,
            "client_id": row.client_id,
            "merchant_id": row.merchant_id,
            "item_name": row.item_name,
            "demand_text": row.demand_text,
            "max_price": row.max_price,
            "quantity": row.quantity,
            "timeout_sec": row.timeout_sec,
            "status": row.status.value if hasattr(row.status, "value") else str(row.status),
            "offer_id": row.offer_id,
            "final_price": row.final_price,
            "created_at": row.created_at,
            "executed_at": row.executed_at,
            "error_reason": row.error_reason,
            "audit_hash": row.audit_hash,
        }
