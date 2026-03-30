from __future__ import annotations

import json
import os
import time
import uuid
from datetime import date, datetime, time as dt_time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import Boolean, Date, DateTime, Numeric, String, Text, UniqueConstraint, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from shared.claw_protocol import BillingStatus, TransactionEvent


class Base(DeclarativeBase):
    pass


class MerchantAccount(Base):
    __tablename__ = "merchant_accounts"

    merchant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    promoter_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    balance: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=Decimal("0"))
    is_frozen: Mapped[bool] = mapped_column(Boolean, default=False)
    currency_unit: Mapped[str] = mapped_column(String(16), default="Token")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class PromoterWallet(Base):
    __tablename__ = "promoter_wallets"

    promoter_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    parent_promoter_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    wallet_balance: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=Decimal("0"))
    withdrawable_amount: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=Decimal("0"))
    frozen_amount: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=Decimal("0"))
    settled_amount: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=Decimal("0"))
    level_depth: Mapped[int] = mapped_column(default=1)
    role_label: Mapped[str] = mapped_column(String(32), default="中间商/包工头")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    __table_args__ = (
        UniqueConstraint("merchant_id", "trade_id", name="ux_ledger_entries_merchant_trade"),
    )

    entry_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    transaction_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    merchant_id: Mapped[str] = mapped_column(String(64), index=True)
    promoter_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    trade_id: Mapped[str] = mapped_column(String(64), index=True)

    amount: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    reason: Mapped[str] = mapped_column(String(128), default="成交路由费")

    routing_fee_ratio: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0.10"))
    platform_profit_ratio: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0.20"))
    promoter_profit_ratio: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0.80"))
    platform_profit: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=Decimal("0"))
    promoter_profit: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=Decimal("0"))
    profit_owner: Mapped[str] = mapped_column(String(64), default="Platform_Profit")

    before_balance: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=Decimal("0"))
    after_balance: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=Decimal("0"))

    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    audit_log: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class SettlementReport(Base):
    __tablename__ = "settlement_reports"
    __table_args__ = (
        UniqueConstraint("report_date", "beneficiary_id", "beneficiary_type", name="ux_settlement_report_unique"),
    )

    report_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    report_date: Mapped[date] = mapped_column(Date, index=True)
    beneficiary_id: Mapped[str] = mapped_column(String(64), index=True)
    beneficiary_type: Mapped[str] = mapped_column(String(32), index=True)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=Decimal("0"))
    entry_count: Mapped[int] = mapped_column(default=0)
    settlement_status: Mapped[str] = mapped_column(String(16), default="pending")
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    detail_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class WithdrawRequest(Base):
    __tablename__ = "withdraw_requests"

    request_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    promoter_id: Mapped[str] = mapped_column(String(64), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    account_info: Mapped[str] = mapped_column(Text, default="{}")
    note: Mapped[str] = mapped_column(Text, default="")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class CommissionPayout(Base):
    __tablename__ = "commission_payouts"

    payout_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    transaction_id: Mapped[str] = mapped_column(String(64), index=True)
    merchant_id: Mapped[str] = mapped_column(String(64), index=True)
    trade_id: Mapped[str] = mapped_column(String(64), index=True)
    source_promoter_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    beneficiary_promoter_id: Mapped[str] = mapped_column(String(64), index=True)
    level_index: Mapped[int] = mapped_column(default=1)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=Decimal("0"))
    settlement_status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class LedgerManager:
    def __init__(self):
        db_url = os.getenv("LEDGER_DATABASE_URL", "") or os.getenv("CLEARING_DATABASE_URL", "")
        if not db_url:
            db_url = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/project_claw"

        self.engine = create_async_engine(db_url, pool_pre_ping=True)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False, class_=AsyncSession)

        self.quote_min_token = self._d(os.getenv("LEDGER_QUOTE_MIN_TOKEN", "1"))
        self.routing_fee_ratio = self._d(os.getenv("LEDGER_ROUTING_FEE_RATIO", "0.10"))
        self.platform_profit_ratio = self._d(os.getenv("LEDGER_PLATFORM_PROFIT_RATIO", "0.20"))
        self.promoter_profit_ratio = self._d(os.getenv("LEDGER_PROMOTER_PROFIT_RATIO", "0.80"))
        self.default_reason = os.getenv("LEDGER_DEDUCT_REASON", "成交路由费")
        self.default_platform_account = os.getenv("LEDGER_PLATFORM_ACCOUNT", "Platform_Profit")
        self.default_promoter_role = os.getenv("LEDGER_PROMOTER_ROLE", "中间商/包工头")
        self.promoter_level_ratios = [self._d(x.strip()) for x in os.getenv("LEDGER_PROMOTER_LEVEL_RATIOS", "0.50,0.30").split(",") if x.strip()]

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _d(v: str | float | Decimal) -> Decimal:
        return Decimal(str(v)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

    @staticmethod
    def _txn_id() -> str:
        return f"txn_{uuid.uuid4().hex[:16]}"

    @staticmethod
    def _append_audit(raw: str, event: str, **fields) -> str:
        try:
            data = json.loads(raw or "[]")
        except Exception:
            data = []
        data.append({"ts": time.time(), "event": event, **fields})
        return json.dumps(data, ensure_ascii=False)

    @staticmethod
    def _event(row: LedgerEntry) -> TransactionEvent:
        return TransactionEvent(
            transaction_id=row.transaction_id,
            trade_id=row.trade_id,
            amount=float(row.amount),
            reason=row.reason,
            timestamp=time.time(),
        )

    @staticmethod
    def _status(row: MerchantAccount) -> BillingStatus:
        return BillingStatus(
            balance=float(row.balance),
            is_frozen=bool(row.is_frozen),
            currency_unit=row.currency_unit,
        )

    async def init_models(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ledger_entries_merchant_created ON ledger_entries(merchant_id, created_at)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_settlement_reports_date_type ON settlement_reports(report_date, beneficiary_type)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_commission_payouts_beneficiary_created ON commission_payouts(beneficiary_promoter_id, created_at)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_withdraw_requests_promoter_created ON withdraw_requests(promoter_id, created_at)"))

    def compute_deduct_amount(self, trade_price: float) -> float:
        price = self._d(trade_price)
        amount = (price * self.routing_fee_ratio).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        return float(max(amount, self._d("0.000001")))

    async def _ensure_promoter_wallet(self, session: AsyncSession, promoter_id: str, parent_promoter_id: str = "", role_label: str = "") -> Optional[PromoterWallet]:
        promoter_id = (promoter_id or "").strip()
        if not promoter_id:
            return None
        q = await session.execute(select(PromoterWallet).where(PromoterWallet.promoter_id == promoter_id).with_for_update())
        row = q.scalar_one_or_none()
        if row is None:
            parent = (parent_promoter_id or "").strip()
            parent_wallet = await self._ensure_promoter_wallet(session, parent) if parent else None
            row = PromoterWallet(
                promoter_id=promoter_id,
                parent_promoter_id=parent,
                wallet_balance=Decimal("0"),
                withdrawable_amount=Decimal("0"),
                frozen_amount=Decimal("0"),
                settled_amount=Decimal("0"),
                level_depth=(parent_wallet.level_depth + 1) if parent_wallet else 1,
                role_label=role_label or self.default_promoter_role,
                created_at=self._now(),
                updated_at=self._now(),
            )
            session.add(row)
            await session.flush()
        else:
            if parent_promoter_id and not row.parent_promoter_id:
                parent = parent_promoter_id.strip()
                parent_wallet = await self._ensure_promoter_wallet(session, parent) if parent else None
                row.parent_promoter_id = parent
                row.level_depth = (parent_wallet.level_depth + 1) if parent_wallet else 1
            if role_label:
                row.role_label = role_label
        return row

    async def _ensure_account(self, session: AsyncSession, merchant_id: str, promoter_id: str = "") -> MerchantAccount:
        q = await session.execute(
            select(MerchantAccount)
            .where(MerchantAccount.merchant_id == merchant_id)
            .with_for_update()
        )
        row = q.scalar_one_or_none()
        if row is None:
            row = MerchantAccount(
                merchant_id=merchant_id,
                promoter_id=(promoter_id or "").strip(),
                balance=Decimal("0"),
                is_frozen=False,
                currency_unit="Token",
                created_at=self._now(),
                updated_at=self._now(),
            )
            session.add(row)
            await session.flush()
        elif promoter_id and not row.promoter_id:
            row.promoter_id = promoter_id.strip()
            row.updated_at = self._now()
        if row.promoter_id:
            await self._ensure_promoter_wallet(session, row.promoter_id)
        return row

    async def register_promoter(self, promoter_id: str, parent_promoter_id: str = "", role_label: str = "") -> dict:
        async with self.session_factory() as session:
            async with session.begin():
                wallet = await self._ensure_promoter_wallet(session, promoter_id, parent_promoter_id, role_label)
                return {
                    "promoter_id": wallet.promoter_id,
                    "parent_promoter_id": wallet.parent_promoter_id,
                    "role_label": wallet.role_label,
                    "level_depth": wallet.level_depth,
                    "wallet_balance": float(wallet.wallet_balance),
                    "withdrawable_amount": float(wallet.withdrawable_amount),
                    "frozen_amount": float(wallet.frozen_amount),
                    "settled_amount": float(wallet.settled_amount),
                }

    async def _get_promoter_chain(self, session: AsyncSession, promoter_id: str, max_depth: int = 5) -> list[PromoterWallet]:
        chain: list[PromoterWallet] = []
        current = (promoter_id or "").strip()
        seen: set[str] = set()
        while current and current not in seen and len(chain) < max_depth:
            seen.add(current)
            wallet = await self._ensure_promoter_wallet(session, current)
            if wallet is None:
                break
            chain.append(wallet)
            current = (wallet.parent_promoter_id or "").strip()
        return chain

    def _allocate_promoter_profit(self, total: Decimal, chain: list[PromoterWallet]) -> list[tuple[PromoterWallet, Decimal, int]]:
        if total <= 0 or not chain:
            return []
        shares: list[tuple[PromoterWallet, Decimal, int]] = []
        remaining = total
        for idx, wallet in enumerate(chain):
            ratio = self.promoter_level_ratios[idx] if idx < len(self.promoter_level_ratios) else Decimal("0")
            if idx == len(chain) - 1:
                amount = remaining
            else:
                amount = (total * ratio).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
                if amount > remaining:
                    amount = remaining
            remaining = (remaining - amount).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
            shares.append((wallet, amount, idx + 1))
            if remaining <= 0:
                break
        return shares

    async def register_merchant(self, merchant_id: str, promoter_id: str = "") -> BillingStatus:
        async with self.session_factory() as session:
            async with session.begin():
                account = await self._ensure_account(session, merchant_id, promoter_id)
                return self._status(account)

    async def check_balance(self, merchant_id: str) -> tuple[bool, BillingStatus]:
        async with self.session_factory() as session:
            async with session.begin():
                account = await self._ensure_account(session, merchant_id)
                enough = (not account.is_frozen) and account.balance >= self.quote_min_token
                return enough, self._status(account)

    async def top_up(self, merchant_id: str, amount: float, promoter_id: str = "") -> BillingStatus:
        add = self._d(amount)
        if add <= 0:
            raise ValueError("top_up_amount_must_be_positive")

        async with self.session_factory() as session:
            async with session.begin():
                account = await self._ensure_account(session, merchant_id, promoter_id)
                account.balance = (account.balance + add).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
                account.updated_at = self._now()
                return self._status(account)

    async def deduct_routing_token(self, merchant_id: str, amount: float, trade_id: str) -> tuple[BillingStatus, TransactionEvent]:
        amt = self._d(amount)
        if amt <= 0:
            raise ValueError("deduct_amount_must_be_positive")
        if not trade_id:
            raise ValueError("trade_id_required")

        idempotency_key = f"deduct:{merchant_id}:{trade_id}"

        async with self.session_factory() as session:
            async with session.begin():
                existing_q = await session.execute(
                    select(LedgerEntry)
                    .where(LedgerEntry.idempotency_key == idempotency_key)
                    .with_for_update()
                )
                existing = existing_q.scalar_one_or_none()
                if existing is not None:
                    acct = await self._ensure_account(session, merchant_id)
                    return self._status(acct), self._event(existing)

                account = await self._ensure_account(session, merchant_id)
                if account.is_frozen:
                    raise RuntimeError("merchant_account_frozen")
                if account.balance < amt:
                    raise RuntimeError("insufficient_token_balance")

                promoter_chain = await self._get_promoter_chain(session, account.promoter_id)
                before = account.balance
                after = (before - amt).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
                account.balance = after
                account.updated_at = self._now()

                platform_profit = (amt * self.platform_profit_ratio).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
                promoter_profit = (amt * self.promoter_profit_ratio).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
                if platform_profit + promoter_profit != amt:
                    promoter_profit = (amt - platform_profit).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

                payout_details = []
                for wallet, share_amount, level_index in self._allocate_promoter_profit(promoter_profit, promoter_chain):
                    if share_amount <= 0:
                        continue
                    wallet.wallet_balance = (wallet.wallet_balance + share_amount).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
                    wallet.withdrawable_amount = (wallet.withdrawable_amount + share_amount).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
                    wallet.updated_at = self._now()
                    payout = CommissionPayout(
                        payout_id=uuid.uuid4().hex,
                        transaction_id=self._txn_id(),
                        merchant_id=merchant_id,
                        trade_id=trade_id,
                        source_promoter_id=account.promoter_id or "",
                        beneficiary_promoter_id=wallet.promoter_id,
                        level_index=level_index,
                        amount=share_amount,
                        settlement_status="pending",
                        created_at=self._now(),
                    )
                    session.add(payout)
                    payout_details.append({
                        "promoter_id": wallet.promoter_id,
                        "level_index": level_index,
                        "amount": float(share_amount),
                        "role": wallet.role_label,
                    })

                row = LedgerEntry(
                    entry_id=uuid.uuid4().hex,
                    transaction_id=self._txn_id(),
                    merchant_id=merchant_id,
                    promoter_id=account.promoter_id or "",
                    trade_id=trade_id,
                    amount=amt,
                    reason=self.default_reason,
                    routing_fee_ratio=self.routing_fee_ratio,
                    platform_profit_ratio=self.platform_profit_ratio,
                    promoter_profit_ratio=self.promoter_profit_ratio,
                    platform_profit=platform_profit,
                    promoter_profit=promoter_profit,
                    profit_owner=self.default_platform_account,
                    before_balance=before,
                    after_balance=after,
                    idempotency_key=idempotency_key,
                    audit_log=self._append_audit("[]", "token_deducted", merchant_id=merchant_id, promoter_id=account.promoter_id, amount=float(amt), platform_profit=float(platform_profit), promoter_profit=float(promoter_profit), payouts=payout_details),
                    created_at=self._now(),
                )
                session.add(row)
                await session.flush()
                return self._status(account), self._event(row)

    async def deduct_routing_token(self, merchant_id: str, amount: float, trade_id: str) -> tuple[BillingStatus, TransactionEvent]:
        # backward compatibility alias
        return await self.deduct_routing_token(merchant_id, amount, trade_id)

    async def deduct_token(self, merchant_id: str, amount: float, trade_id: str) -> tuple[BillingStatus, TransactionEvent]:
        # backward compatibility alias
        return await self.deduct_routing_token(merchant_id, amount, trade_id)

    async def deduct_token(self, merchant_id: str, amount: float, trade_id: str) -> tuple[BillingStatus, TransactionEvent]:
        # backward compatibility alias
        return await self.deduct_routing_token(merchant_id, amount, trade_id)

    async def generate_settlement_report(self, report_date: Optional[date] = None) -> dict:
        target = report_date or (self._now() - timedelta(days=1)).date()
        start = datetime.combine(target, dt_time.min, tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        async with self.session_factory() as session:
            async with session.begin():
                p_total = self._d(await session.scalar(select(func.coalesce(func.sum(LedgerEntry.platform_profit), 0)).where(LedgerEntry.created_at >= start).where(LedgerEntry.created_at < end)) or 0)
                p_count = int((await session.scalar(select(func.count(LedgerEntry.entry_id)).where(LedgerEntry.created_at >= start).where(LedgerEntry.created_at < end))) or 0)
                payout_rows = (await session.execute(select(CommissionPayout.beneficiary_promoter_id, func.coalesce(func.sum(CommissionPayout.amount), 0), func.count(CommissionPayout.payout_id)).where(CommissionPayout.created_at >= start).where(CommissionPayout.created_at < end).group_by(CommissionPayout.beneficiary_promoter_id))).all()
                await session.execute(text("DELETE FROM settlement_reports WHERE report_date = :report_date"), {"report_date": target})
                session.add(SettlementReport(report_id=uuid.uuid4().hex, report_date=target, beneficiary_id=self.default_platform_account, beneficiary_type="platform", total_amount=p_total, entry_count=p_count, settlement_status="pending", detail_json=json.dumps({"source": "daily_settlement"}, ensure_ascii=False), created_at=self._now()))
                details = {"report_date": str(target), "platform_profit": float(p_total), "platform_entry_count": p_count, "promoters": []}
                for promoter_id, total_amount, entry_count in payout_rows:
                    wallet = await self._ensure_promoter_wallet(session, str(promoter_id))
                    total = self._d(total_amount or 0)
                    cnt = int(entry_count or 0)
                    details["promoters"].append({"promoter_id": promoter_id, "total_amount": float(total), "entry_count": cnt, "role": wallet.role_label if wallet else self.default_promoter_role, "withdrawable_amount": float(wallet.withdrawable_amount) if wallet else 0.0, "settled_amount": float(wallet.settled_amount) if wallet else 0.0})
                    session.add(SettlementReport(report_id=uuid.uuid4().hex, report_date=target, beneficiary_id=str(promoter_id), beneficiary_type="promoter", total_amount=total, entry_count=cnt, settlement_status="pending", detail_json=json.dumps({"role": wallet.role_label if wallet else self.default_promoter_role}, ensure_ascii=False), created_at=self._now()))
                return details

    async def wallet_snapshot(self, promoter_id: str) -> dict:
        async with self.session_factory() as session:
            async with session.begin():
                wallet = await self._ensure_promoter_wallet(session, promoter_id)
                if wallet is None:
                    raise ValueError("promoter_id_required")
                return {"promoter_id": wallet.promoter_id, "parent_promoter_id": wallet.parent_promoter_id, "role_label": wallet.role_label, "level_depth": wallet.level_depth, "wallet_balance": float(wallet.wallet_balance), "withdrawable_amount": float(wallet.withdrawable_amount), "frozen_amount": float(wallet.frozen_amount), "settled_amount": float(wallet.settled_amount)}

    async def mark_settlement_paid(self, report_date: date, beneficiary_id: str, beneficiary_type: str = "promoter") -> dict:
        async with self.session_factory() as session:
            async with session.begin():
                q = await session.execute(select(SettlementReport).where(SettlementReport.report_date == report_date).where(SettlementReport.beneficiary_id == beneficiary_id).where(SettlementReport.beneficiary_type == beneficiary_type).with_for_update())
                row = q.scalar_one_or_none()
                if row is None:
                    raise ValueError("settlement_report_not_found")
                row.settlement_status = "paid"
                row.paid_at = self._now()
                if beneficiary_type == "promoter":
                    wallet = await self._ensure_promoter_wallet(session, beneficiary_id)
                    paid_amount = self._d(row.total_amount or 0)
                    wallet.withdrawable_amount = max(Decimal("0"), (wallet.withdrawable_amount - paid_amount).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))
                    wallet.settled_amount = (wallet.settled_amount + paid_amount).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
                    wallet.updated_at = self._now()
                    payouts = (await session.execute(select(CommissionPayout).where(CommissionPayout.beneficiary_promoter_id == beneficiary_id).where(CommissionPayout.settlement_status == "pending").where(CommissionPayout.created_at >= datetime.combine(report_date, dt_time.min, tzinfo=timezone.utc)).where(CommissionPayout.created_at < datetime.combine(report_date, dt_time.min, tzinfo=timezone.utc) + timedelta(days=1)).with_for_update())).scalars().all()
                    for payout in payouts:
                        payout.settlement_status = "paid"
                return {"report_date": str(report_date), "beneficiary_id": beneficiary_id, "beneficiary_type": beneficiary_type, "settlement_status": row.settlement_status, "paid_at": row.paid_at.isoformat() if row.paid_at else None}


    async def create_withdraw_request(self, promoter_id: str, amount: float, account_info: dict | None = None, note: str = "") -> dict:
        amt = self._d(amount)
        if amt <= 0:
            raise ValueError("withdraw_amount_must_be_positive")
        async with self.session_factory() as session:
            async with session.begin():
                wallet = await self._ensure_promoter_wallet(session, promoter_id)
                if wallet is None:
                    raise ValueError("promoter_id_required")
                if wallet.withdrawable_amount < amt:
                    raise RuntimeError("insufficient_withdrawable_amount")
                wallet.withdrawable_amount = (wallet.withdrawable_amount - amt).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
                wallet.frozen_amount = (wallet.frozen_amount + amt).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
                wallet.updated_at = self._now()
                row = WithdrawRequest(request_id=uuid.uuid4().hex, promoter_id=promoter_id, amount=amt, status="pending", account_info=json.dumps(account_info or {}, ensure_ascii=False), note=note, created_at=self._now())
                session.add(row)
                await session.flush()
                return {"request_id": row.request_id, "promoter_id": promoter_id, "amount": float(row.amount), "status": row.status}

    async def list_withdraw_requests(self, promoter_id: str = "") -> list[dict]:
        async with self.session_factory() as session:
            async with session.begin():
                stmt = select(WithdrawRequest).order_by(WithdrawRequest.created_at.desc())
                if promoter_id:
                    stmt = stmt.where(WithdrawRequest.promoter_id == promoter_id)
                rows = (await session.execute(stmt)).scalars().all()
                return [{"request_id": r.request_id, "promoter_id": r.promoter_id, "amount": float(r.amount), "status": r.status, "account_info": json.loads(r.account_info or "{}"), "note": r.note, "created_at": r.created_at.isoformat() if r.created_at else None, "approved_at": r.approved_at.isoformat() if r.approved_at else None, "paid_at": r.paid_at.isoformat() if r.paid_at else None, "rejected_at": r.rejected_at.isoformat() if r.rejected_at else None} for r in rows]

    async def approve_withdraw_request(self, request_id: str) -> dict:
        async with self.session_factory() as session:
            async with session.begin():
                row = (await session.execute(select(WithdrawRequest).where(WithdrawRequest.request_id == request_id).with_for_update())).scalar_one_or_none()
                if row is None:
                    raise ValueError("withdraw_request_not_found")
                if row.status != "pending":
                    raise RuntimeError("withdraw_request_not_pending")
                row.status = "approved"
                row.approved_at = self._now()
                return {"request_id": row.request_id, "status": row.status}

    async def reject_withdraw_request(self, request_id: str, note: str = "") -> dict:
        async with self.session_factory() as session:
            async with session.begin():
                row = (await session.execute(select(WithdrawRequest).where(WithdrawRequest.request_id == request_id).with_for_update())).scalar_one_or_none()
                if row is None:
                    raise ValueError("withdraw_request_not_found")
                if row.status not in ("pending", "approved"):
                    raise RuntimeError("withdraw_request_not_rejectable")
                wallet = await self._ensure_promoter_wallet(session, row.promoter_id)
                wallet.frozen_amount = max(Decimal("0"), (wallet.frozen_amount - row.amount).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))
                wallet.withdrawable_amount = (wallet.withdrawable_amount + row.amount).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
                wallet.updated_at = self._now()
                row.status = "rejected"
                row.rejected_at = self._now()
                if note:
                    row.note = note
                return {"request_id": row.request_id, "status": row.status}

    async def pay_withdraw_request(self, request_id: str) -> dict:
        async with self.session_factory() as session:
            async with session.begin():
                row = (await session.execute(select(WithdrawRequest).where(WithdrawRequest.request_id == request_id).with_for_update())).scalar_one_or_none()
                if row is None:
                    raise ValueError("withdraw_request_not_found")
                if row.status not in ("approved", "pending"):
                    raise RuntimeError("withdraw_request_not_payable")
                wallet = await self._ensure_promoter_wallet(session, row.promoter_id)
                wallet.frozen_amount = max(Decimal("0"), (wallet.frozen_amount - row.amount).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))
                wallet.settled_amount = (wallet.settled_amount + row.amount).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
                wallet.updated_at = self._now()
                row.status = "paid"
                row.paid_at = self._now()
                return {"request_id": row.request_id, "status": row.status, "paid_at": row.paid_at.isoformat() if row.paid_at else None}
