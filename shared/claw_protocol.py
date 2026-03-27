from __future__ import annotations

import hashlib
import hmac
import json
import time
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Decision(str, Enum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"


class DialogueRole(str, Enum):
    CLIENT = "CLIENT"
    MERCHANT = "MERCHANT"
    ORCHESTRATOR = "ORCHESTRATOR"


class DialogueSessionStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class A2ABaseModel(BaseModel):
    """Strict base model for A2A handshake payloads."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, validate_assignment=True)


class A2A_TradeIntent(A2ABaseModel):
    """买方询价包。"""

    intent_id: UUID = Field(default_factory=uuid4, description="询价单唯一 ID（UUID）")
    client_id: str = Field(..., min_length=1, max_length=64, description="买方客户端 ID")
    item_name: str = Field(..., min_length=1, max_length=128, description="商品名")
    expected_price: float = Field(..., gt=0, description="买方期望价格，必须大于 0")
    max_distance_km: float = Field(..., gt=0, le=200, description="可接受最大距离（公里）")
    timestamp: float = Field(default_factory=time.time, gt=0, description="Unix 时间戳")


class A2A_MerchantOffer(A2ABaseModel):
    """卖方报价包。"""

    offer_id: UUID = Field(default_factory=uuid4, description="报价唯一 ID")
    intent_id: UUID = Field(..., description="关联的询价单 intent_id")
    merchant_id: str = Field(..., min_length=1, max_length=64, description="商家 ID")
    offered_price: float = Field(..., gt=0, description="最终报价，必须大于 0")
    is_accepted: bool = Field(..., description="是否接单")
    reason: str = Field(default="", max_length=256, description="给买家的附言，例如：加送煎蛋")

    @field_validator("reason")
    @classmethod
    def _normalize_reason(cls, value: str) -> str:
        return value.strip()


class A2A_TradeDecision(A2ABaseModel):
    """买方决断包。"""

    offer_id: UUID = Field(..., description="被决策的报价 ID")
    client_id: str = Field(..., min_length=1, max_length=64, description="买方客户端 ID")
    decision: Decision = Field(..., description="买方决策：ACCEPT 或 REJECT")


class A2A_DialogueSession(A2ABaseModel):
    session_id: UUID = Field(default_factory=uuid4)
    intent_id: UUID = Field(...)
    client_id: str = Field(..., min_length=1, max_length=64)
    merchant_id: str = Field(..., min_length=1, max_length=64)
    item_name: str = Field(..., min_length=1, max_length=128)
    status: DialogueSessionStatus = Field(default=DialogueSessionStatus.OPEN)
    round: int = Field(default=0, ge=0, le=20)
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)


class A2A_DialogueTurn(A2ABaseModel):
    turn_id: UUID = Field(default_factory=uuid4)
    session_id: UUID = Field(...)
    intent_id: UUID = Field(...)
    round: int = Field(..., ge=1, le=20)
    sender_role: DialogueRole = Field(...)
    sender_id: str = Field(..., min_length=1, max_length=64)
    receiver_role: DialogueRole = Field(...)
    receiver_id: str = Field(..., min_length=1, max_length=64)
    text: str = Field(..., min_length=1, max_length=500)
    expected_price: float | None = Field(default=None, gt=0)
    offered_price: float | None = Field(default=None, gt=0)
    strategy_hint: str = Field(default="", max_length=256)
    timestamp: float = Field(default_factory=time.time)


class A2A_StartDialogueRequest(A2ABaseModel):
    intent: A2A_TradeIntent
    merchant_id: str = Field(..., min_length=1, max_length=64)
    opening_text: str = Field(default="请给我一个更好的方案")


class A2A_ClientTurnRequest(A2ABaseModel):
    session_id: UUID
    client_id: str = Field(..., min_length=1, max_length=64)
    text: str = Field(..., min_length=1, max_length=500)
    expected_price: float | None = Field(default=None, gt=0)


class A2A_DialogueSessionView(A2ABaseModel):
    session: A2A_DialogueSession
    turns: list[A2A_DialogueTurn] = Field(default_factory=list)


def sign_payload(payload: BaseModel | dict[str, Any], secret: str) -> str:
    """对 payload 的标准 JSON 进行 HMAC-SHA256 签名。"""

    if not secret:
        raise ValueError("secret must not be empty")

    if isinstance(payload, BaseModel):
        data = payload.model_dump(mode="json")
    elif isinstance(payload, dict):
        data = payload
    else:
        raise TypeError("payload must be a pydantic model or dict")

    message = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest
