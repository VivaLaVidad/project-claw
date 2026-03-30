from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional

from sqlalchemy import DateTime, Numeric, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from cloud_server.ledger_service import LedgerEntry, LedgerManager


class Base(DeclarativeBase):
    pass


class ClearingLedger(Base):
    __tablename__ = "clearing_ledger"

    ledger_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    trade_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    client_id: Mapped[str] = mapped_column(String(64), index=True)
    merchant_id: Mapped[str] = mapped_column(String(64), index=True)
    promoter_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    final_price: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(32), default="prepay_created", index=True)
    out_trade_no: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    wechat_transaction_id: Mapped[str] = mapped_column(String(80), default="", index=True)
    payment_qr_url: Mapped[str] = mapped_column(Text, default="")
    merchant_share: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=Decimal("0"))
    promoter_share: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=Decimal("0"))
    platform_share: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=Decimal("0"))
    audit_hash: Mapped[str] = mapped_column(String(128), default="")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    error_reason: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class WechatPayProvider(ABC):
    @abstractmethod
    async def create_prepay_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        ...


class MockWechatPayProvider(WechatPayProvider):
    async def create_prepay_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        out_trade_no = payload["out_trade_no"]
        return {
            "out_trade_no": out_trade_no,
            "payment_qr_url": f"weixin://wxpay/bizpayurl?pr={out_trade_no}",
            "prepay_id": f"mock_prepay_{uuid.uuid4().hex[:16]}",
        }


class ClearingService:
    def __init__(self, provider: Optional[WechatPayProvider] = None):
        db_url = os.getenv("CLEARING_DATABASE_URL", "") or os.getenv("DATABASE_URL", "")
        if db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if not db_url:
            db_url = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/project_claw"

        self.engine = create_async_engine(db_url, pool_pre_ping=True)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False, class_=AsyncSession)
        self.ledger_manager = LedgerManager()
        self.provider = provider or MockWechatPayProvider()

    @staticmethod
    def _d(v: Any) -> Decimal:
        return Decimal(str(v)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _audit_hash(payload: dict[str, Any]) -> str:
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    @staticmethod
    def _profit_sharing(total: Decimal) -> tuple[Decimal, Decimal, Decimal]:
        merchant = (total * Decimal("0.99")).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        promoter = (total * Decimal("0.008")).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        platform = (total - merchant - promoter).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        return merchant, promoter, platform

    async def init_models(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await self.ledger_manager.init_models()

    async def create_prepay_for_trade(
        self,
        request_id: str,
        trade_id: str,
        client_id: str,
        merchant_id: str,
        final_price: float,
        promoter_id: str = "",
    ) -> dict[str, Any]:
        amount = self._d(final_price)
        merchant_share, promoter_share, platform_share = self._profit_sharing(amount)
        out_trade_no = f"PC{int(time.time())}{uuid.uuid4().hex[:8]}"
        payload = {
            "appid": os.getenv("WECHAT_APP_ID", "wx_project_claw"),
            "mchid": os.getenv("WECHAT_MCH_ID", "service_provider_mch"),
            "description": f"Project Claw trade {trade_id}",
            "out_trade_no": out_trade_no,
            "notify_url": os.getenv("WECHAT_NOTIFY_URL", "https://example.com/callback"),
            "amount": {"total": int((amount * 100).to_integral_value()), "currency": "CNY"},
            "settle_info": {"profit_sharing": True},
            "receivers": [
                {"merchant_id": merchant_id, "ratio": 99.0},
                {"promoter_id": promoter_id, "ratio": 0.8},
                {"platform_id": os.getenv("PLATFORM_MCH_ID", "platform"), "ratio": 0.2},
            ],
        }

        wx = await self.provider.create_prepay_order(payload)
        async with self.session_factory() as session:
            async with session.begin():
                old = (await session.execute(select(ClearingLedger).where(ClearingLedger.trade_id == trade_id).with_for_update())).scalar_one_or_none()
                if old is not None:
                    return {
                        "ledger_id": old.ledger_id,
                        "out_trade_no": old.out_trade_no,
                        "payment_qr_url": old.payment_qr_url,
                        "profit_sharing": {"merchant": float(old.merchant_share), "promoter": float(old.promoter_share), "platform": float(old.platform_share)},
                        "route_fee_cents": int((old.platform_share * 100).to_integral_value()),
                    }

                row = ClearingLedger(
                    ledger_id=uuid.uuid4().hex,
                    request_id=request_id,
                    trade_id=trade_id,
                    client_id=client_id,
                    merchant_id=merchant_id,
                    promoter_id=promoter_id,
                    final_price=amount,
                    status="prepay_created",
                    out_trade_no=out_trade_no,
                    payment_qr_url=wx["payment_qr_url"],
                    merchant_share=merchant_share,
                    promoter_share=promoter_share,
                    platform_share=platform_share,
                    audit_hash=self._audit_hash(payload),
                    payload_json=json.dumps(payload, ensure_ascii=False),
                    created_at=self._now(),
                    updated_at=self._now(),
                )
                session.add(row)
                await session.flush()
                return {
                    "ledger_id": row.ledger_id,
                    "out_trade_no": row.out_trade_no,
                    "payment_qr_url": row.payment_qr_url,
                    "profit_sharing": {"merchant": float(merchant_share), "promoter": float(promoter_share), "platform": float(platform_share)},
                    "route_fee_cents": int((platform_share * 100).to_integral_value()),
                }

    async def parse_wechat_webhook(self, payload_bytes: bytes) -> dict[str, Any]:
        data = json.loads(payload_bytes.decode("utf-8"))
        return {
            "out_trade_no": data.get("out_trade_no", ""),
            "transaction_id": data.get("transaction_id", ""),
            "trade_state": data.get("trade_state", "SUCCESS"),
        }

    async def parse_wechat_webhook_v3(self, payload_bytes: bytes, headers: dict[str, str]) -> dict[str, Any]:
        _ = headers
        return await self.parse_wechat_webhook(payload_bytes)

    async def mark_paid(self, out_trade_no: str, wechat_transaction_id: str) -> str:
        async with self.session_factory() as session:
            async with session.begin():
                row = (await session.execute(select(ClearingLedger).where(ClearingLedger.out_trade_no == out_trade_no).with_for_update())).scalar_one_or_none()
                if row is None:
                    raise KeyError(out_trade_no)
                row.status = "paid"
                row.wechat_transaction_id = wechat_transaction_id
                row.updated_at = self._now()
                return row.ledger_id

    async def deduct_routing_token(self, merchant_id: str, amount: float, trade_id: str):
        # uses db-level lock + idempotency in LedgerManager.deduct_routing_token
        return await self.ledger_manager.deduct_routing_token(merchant_id=merchant_id, amount=amount, trade_id=trade_id)

    async def settle_promoter_commission(self, ledger_id: str):
        async with self.session_factory() as session:
            async with session.begin():
                row = (await session.execute(select(ClearingLedger).where(ClearingLedger.ledger_id == ledger_id).with_for_update())).scalar_one_or_none()
                if row is None:
                    raise ValueError("ledger_not_found")
                if row.status not in {"paid", "commission_pending"}:
                    return {"ok": True, "ledger_id": ledger_id, "status": row.status}
                row.status = "commission_pending"

        await self.deduct_routing_token(row.merchant_id, float(row.platform_share), row.trade_id)

        async with self.session_factory() as session:
            async with session.begin():
                row2 = (await session.execute(select(ClearingLedger).where(ClearingLedger.ledger_id == ledger_id).with_for_update())).scalar_one_or_none()
                if row2 is None:
                    raise ValueError("ledger_not_found")
                row2.status = "settled"
                row2.updated_at = self._now()
        return {"ok": True, "ledger_id": ledger_id, "status": "settled"}

    async def refund_and_unlock(self, trade_id: str, reason: str = "payment_timeout") -> dict[str, Any]:
        async with self.session_factory() as session:
            async with session.begin():
                row = (await session.execute(select(ClearingLedger).where(ClearingLedger.trade_id == trade_id).with_for_update())).scalar_one_or_none()
                if row is None:
                    raise ValueError("ledger_not_found")
                row.status = "refunded"
                row.error_reason = reason
                row.updated_at = self._now()

            async with session.begin():
                entry = (await session.execute(select(LedgerEntry).where(LedgerEntry.merchant_id == row.merchant_id, LedgerEntry.trade_id == trade_id).with_for_update())).scalar_one_or_none()
                if entry is not None:
                    entry.audit_log = json.dumps([{"ts": time.time(), "event": "refund_unlock", "reason": reason}], ensure_ascii=False)
        return {"ok": True, "trade_id": trade_id, "status": "refunded", "reason": reason}
