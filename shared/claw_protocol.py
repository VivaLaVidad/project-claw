from __future__ import annotations

import hashlib
import hmac
import json
import time
from enum import Enum
from typing import Any, List, Optional
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


class TradeStatus(str, Enum):
    PENDING = "pending"
    OFFERED = "offered"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXECUTED = "executed"
    EXPIRED = "expired"


class MsgType(str, Enum):
    TRADE_REQUEST = "trade_request"
    INTENT_BROADCAST = "intent_broadcast"
    MERCHANT_OFFER = "merchant_offer"
    OFFER_BUNDLE = "offer_bundle"
    EXECUTE_TRADE = "execute_trade"
    BILLING_UPDATE = "billing_update"
    HEARTBEAT = "heartbeat"
    ACK = "ack"
    ERROR = "error"


class BillingStatus(BaseModel):
    balance: float = Field(..., description="余额", ge=0)
    is_frozen: bool = Field(False, description="是否冻结")
    currency_unit: str = Field("Token", description="计费单位")


class GeoCoord(BaseModel):
    lat: float = Field(..., description="纬度")
    lng: float = Field(..., description="经度")
    radius_m: int = Field(500, description="搜索半径（米）")


class TradeRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid4())[:8])
    trace_id: str = Field(default_factory=lambda: str(uuid4())[:12])
    idempotency_key: str = Field(default_factory=lambda: str(uuid4()))
    client_id: str = Field(..., description="C端唯一标识（脱敏）")
    item_name: str = Field(..., description="商品名称")
    demand_text: str = Field(..., description="自然语言需求描述")
    max_price: float = Field(..., description="最高可接受价格（元）", gt=0)
    quantity: int = Field(1, description="数量")
    location: Optional[GeoCoord] = Field(None, description="消费者坐标")
    timeout_sec: float = Field(5.0, description="等待 B端响应超时", ge=1, le=30)
    timestamp: float = Field(default_factory=time.time)


class MerchantOffer(BaseModel):
    offer_id: str = Field(default_factory=lambda: str(uuid4())[:8])
    request_id: str = Field(..., description="对应 TradeRequest.request_id")
    merchant_id: str = Field(..., description="B端节点 ID")
    item_name: str = Field(..., description="商品名")
    final_price: float = Field(..., description="最终报价（元）", gt=0)
    floor_price: float = Field(..., description="底价（内部校验用）", gt=0)
    reply_text: str = Field(..., description="商家话术")
    match_score: float = Field(..., description="匹配度评分 0-100", ge=0, le=100)
    eta_minutes: int = Field(0, description="预计出餐/等待分钟")
    viable: bool = Field(True, description="是否可行")
    timestamp: float = Field(default_factory=time.time)

    @property
    def margin(self) -> float:
        return (self.final_price - self.floor_price) / self.final_price


class ExecuteTrade(BaseModel):
    trade_id: str = Field(default_factory=lambda: str(uuid4())[:8])
    request_id: str = Field(..., description="原始 request_id")
    offer_id: str = Field(..., description="选中的 offer_id")
    merchant_id: str = Field(..., description="目标 B端节点 ID")
    client_id: str = Field(..., description="C端标识")
    final_price: float = Field(..., description="确认价格")
    timestamp: float = Field(default_factory=time.time)


class OfferBundle(BaseModel):
    request_id: str
    offers: List[MerchantOffer]
    total_merchants: int
    responded: int
    elapsed_ms: float
    timestamp: float = Field(default_factory=time.time)


class SocialIntent(BaseModel):
    intent_id: str = Field(default_factory=lambda: str(uuid4())[:12])
    client_id: str = Field(..., description="C端用户ID")
    persona_vector: List[float] = Field(..., description="1024维用户画像向量")
    location: GeoCoord = Field(..., description="用户当前位置")
    topic_hint: str = Field("", description="话题偏好")
    timestamp: float = Field(default_factory=time.time)

    @field_validator("persona_vector")
    @classmethod
    def _validate_vector_len(cls, v: List[float]) -> List[float]:
        if len(v) != 1024:
            raise ValueError("persona_vector_must_be_1024")
        return v


class MatchFoundEvent(BaseModel):
    match_id: str = Field(default_factory=lambda: str(uuid4())[:12])
    client_id: str = Field(..., description="接收方client_id")
    peer_client_id: str = Field(..., description="匹配到的对端client_id")
    similarity: float = Field(..., ge=0, le=1)
    distance_m: float = Field(..., ge=0)
    ice_breaker_tip: str = Field(..., description="破冰提示语")
    timestamp: float = Field(default_factory=time.time)


class TransactionEvent(BaseModel):
    transaction_id: str = Field(default_factory=lambda: str(uuid4())[:12])
    trade_id: str = Field(..., description="对应成交 trade_id")
    amount: float = Field(..., description="扣费金额", gt=0)
    reason: str = Field("成交路由费", description="计费原因")
    timestamp: float = Field(default_factory=time.time)


class SignalEnvelope(BaseModel):
    msg_type: MsgType
    sender_id: str
    payload: dict
    msg_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: float = Field(default_factory=time.time)

    @staticmethod
    def wrap(msg_type: MsgType, sender_id: str, model: BaseModel) -> "SignalEnvelope":
        return SignalEnvelope(msg_type=msg_type, sender_id=sender_id, payload=model.model_dump())

    def unwrap_as(self, model_cls):
        return model_cls(**self.payload)


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
