from __future__ import annotations

import enum
import time
from typing import Any, Optional

from sqlalchemy import JSON, Enum, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TradeStatusEnum(str, enum.Enum):
    pending = "pending"
    offered = "offered"
    accepted = "accepted"
    executed = "executed"
    failed = "failed"
    expired = "expired"


class ClientORM(Base):
    __tablename__ = "clients"

    client_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    wechat_openid: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    persona_vector: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    buyer_system_prompt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    taste_preference: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    negotiation_style: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[float] = mapped_column(Float, default=time.time, nullable=False)
    updated_at: Mapped[float] = mapped_column(Float, default=time.time, nullable=False)


class MerchantORM(Base):
    __tablename__ = "merchants"

    merchant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    promoter_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    routing_token_balance: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    box_status: Mapped[str] = mapped_column(String(32), default="online", nullable=False)
    persona_profile: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    sales_system_prompt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    bottom_line_rules: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[float] = mapped_column(Float, default=time.time, nullable=False)
    updated_at: Mapped[float] = mapped_column(Float, default=time.time, nullable=False)


class TradeLedgerORM(Base):
    __tablename__ = "trade_ledger"
    __table_args__ = (
        UniqueConstraint("request_id", name="uq_trade_ledger_request_id"),
    )

    trade_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(80), nullable=False)
    client_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    merchant_id: Mapped[str] = mapped_column(String(64), default="", nullable=False, index=True)
    original_price: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    final_price: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    status: Mapped[TradeStatusEnum] = mapped_column(Enum(TradeStatusEnum), default=TradeStatusEnum.pending, nullable=False, index=True)
    audit_hash: Mapped[str] = mapped_column(String(128), default="", nullable=False)

    offer_id: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    item_name: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    demand_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    max_price: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    timeout_sec: Mapped[float] = mapped_column(Float, default=20.0, nullable=False)
    error_reason: Mapped[str] = mapped_column(String(128), default="", nullable=False)

    created_at: Mapped[float] = mapped_column(Float, default=time.time, nullable=False, index=True)
    executed_at: Mapped[Optional[float]] = mapped_column(Float, nullable=True, index=True)
    updated_at: Mapped[float] = mapped_column(Float, default=time.time, nullable=False)
