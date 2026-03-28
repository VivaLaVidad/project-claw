"""
cloud_server/clearing_service.py
Project Claw v14.3 - 金融级账单清算与分账服务

合规说明：
- 遵循微信支付 V3 分账 API 规范（模拟 Payload）
- Profit Sharing：平台抽佣 1%，商家分账 99%
- EscrowManager 处理资金冻结/解冻/结算状态流转
- 所有金额单位：分（fen），避免浮点精度问题
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from threading import Lock
from typing import Dict, List, Optional

# ─── 常量 ────────────────────────────────────────────────
PLATFORM_MCH_ID     = "platform_1600000000"
PLATFORM_FEE_RATE   = 0.01
MERCHANT_SHARE_RATE = 1 - PLATFORM_FEE_RATE
WECHAT_PAY_API_BASE = "https://api.mch.weixin.qq.com/v3"
SPLIT_BILL_VERSION  = "V3"

# ─── 枚举 ────────────────────────────────────────────────
class EscrowStatus(str, Enum):
    PENDING  = "PENDING"
    FROZEN   = "FROZEN"
    SETTLED  = "SETTLED"
    REFUNDED = "REFUNDED"
    FAILED   = "FAILED"

class SplitBillStatus(str, Enum):
    DRAFT     = "DRAFT"
    SUBMITTED = "SUBMITTED"
    ACCEPTED  = "ACCEPTED"
    FINISHED  = "FINISHED"
    FAILED    = "FAILED"

# ─── 数据模型 ─────────────────────────────────────────────
@dataclass
class SplitReceiver:
    mch_id:      str
    name:        str
    amount:      int
    description: str
    share_rate:  float

@dataclass
class SplitBill:
    bill_id:          str
    intent_id:        str
    transaction_id:   str
    out_order_no:     str
    total_amount:     int
    merchant_amount:  int
    platform_fee:     int
    receivers:        List[SplitReceiver]
    status:           SplitBillStatus = SplitBillStatus.DRAFT
    created_at:       float = field(default_factory=time.time)
    settled_at:       Optional[float] = None
    raw_payload:      Optional[dict]  = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

@dataclass
class EscrowRecord:
    escrow_id:      str
    intent_id:      str
    client_id:      str
    merchant_id:    str
    total_amount:   int
    frozen_at:      Optional[float]  = None
    unfrozen_at:    Optional[float]  = None
    status:         EscrowStatus     = EscrowStatus.PENDING
    split_bill_id:  Optional[str]    = None
    failure_reason: Optional[str]    = None
    audit_log:      List[dict]       = field(default_factory=list)

    def _add_audit(self, action: str, detail: str = "") -> None:
        self.audit_log.append({"ts": time.time(), "action": action, "detail": detail})

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

# ─── 工具函数 ─────────────────────────────────────────────
def yuan_to_fen(yuan: float) -> int:
    return round(yuan * 100)

def fen_to_yuan(fen: int) -> float:
    return round(fen / 100, 2)

def _mask_name(name: str) -> str:
    if len(name) <= 2:
        return name[0] + "*"
    return name[0] + "*" * (len(name) - 2) + name[-1]

def _mock_sign_payload(out_order_no: str, amount: int) -> str:
    raw = f"{out_order_no}|{amount}|{int(time.time())}"
    return "MOCK-SIG-" + hmac.new(
        b"project-claw-signing-key",
        raw.encode(),
        hashlib.sha256,
    ).hexdigest()[:32].upper()

# ─── generate_split_bill ─────────────────────────────────
def generate_split_bill(
    intent_id: str,
    merchant_id: str,
    merchant_name: str,
    final_price_yuan: float,
    transaction_id: Optional[str] = None,
    platform_fee_rate: float = PLATFORM_FEE_RATE,
) -> SplitBill:
    """
    生成微信支付 V3 分账 Payload。
    total_amount    = round(final_price * 100)
    platform_fee    = max(1, round(total_amount * fee_rate))
    merchant_amount = total_amount - platform_fee
    """
    total_fen    = yuan_to_fen(final_price_yuan)
    platform_fen = max(1, round(total_fen * platform_fee_rate))
    merchant_fen = total_fen - platform_fen
    bill_id      = f"SB-{intent_id[:8]}-{uuid.uuid4().hex[:8].upper()}"
    out_order_no = f"PC{int(time.time())}{uuid.uuid4().hex[:6].upper()}"
    txn_id       = transaction_id or f"MOCK-TXN-{uuid.uuid4().hex[:16].upper()}"

    receivers = [
        SplitReceiver(
            mch_id=merchant_id, name=_mask_name(merchant_name),
            amount=merchant_fen,
            description=f"Project Claw 成交分账 - {merchant_name}",
            share_rate=1 - platform_fee_rate,
        ),
        SplitReceiver(
            mch_id=PLATFORM_MCH_ID, name="Project Claw 平台",
            amount=platform_fen,
            description=f"平台服务费（{platform_fee_rate*100:.0f}%）",
            share_rate=platform_fee_rate,
        ),
    ]

    raw_payload = {
        "api_version":    SPLIT_BILL_VERSION,
        "api_url":        f"{WECHAT_PAY_API_BASE}/profitsharing/orders",
        "appid":          "wx_project_claw",
        "transaction_id": txn_id,
        "out_order_no":   out_order_no,
        "receivers": [
            {"type": "MERCHANT_ID", "account": r.mch_id, "name": r.name,
             "amount": r.amount, "description": r.description}
            for r in receivers
        ],
        "unfreeze_unsplit": False,
        "_meta": {
            "bill_id": bill_id, "intent_id": intent_id,
            "total_amount": total_fen, "merchant_amount": merchant_fen,
            "platform_fee": platform_fen, "fee_rate": platform_fee_rate,
            "generated_at": time.time(),
        },
        "_signature": _mock_sign_payload(out_order_no, total_fen),
    }

    return SplitBill(
        bill_id=bill_id, intent_id=intent_id,
        transaction_id=txn_id, out_order_no=out_order_no,
        total_amount=total_fen, merchant_amount=merchant_fen,
        platform_fee=platform_fen, receivers=receivers,
        status=SplitBillStatus.DRAFT, raw_payload=raw_payload,
    )


# ─── EscrowManager ───────────────────────────────────────
class EscrowManager:
    """
    资金托管管理器。
    状态流转: PENDING → FROZEN → SETTLED / REFUNDED / FAILED
    """
    def __init__(self):
        self._records = {}
        self._lock = Lock()

    def freeze(self, intent_id, client_id, merchant_id, amount_yuan) -> EscrowRecord:
        """冻结资金，等待交付确认"""
        with self._lock:
            escrow_id = f"ESC-{uuid.uuid4().hex[:12].upper()}"
            record = EscrowRecord(
                escrow_id=escrow_id, intent_id=intent_id,
                client_id=client_id, merchant_id=merchant_id,
                total_amount=yuan_to_fen(amount_yuan),
                status=EscrowStatus.FROZEN, frozen_at=time.time(),
            )
            record._add_audit("FREEZE", f"冻结 ¥{amount_yuan} 成功")
            self._records[escrow_id] = record
        return record

    def settle(self, escrow_id, merchant_name="商家", transaction_id=None) -> SplitBill:
        """解冻并生成微信支付 V3 分账单：商家99%，平台1%"""
        with self._lock:
            record = self._get_or_raise(escrow_id)
            if record.status != EscrowStatus.FROZEN:
                raise ValueError(f"[Escrow] {escrow_id} 状态={record.status}，仅FROZEN可结算")
            bill = generate_split_bill(
                intent_id=record.intent_id, merchant_id=record.merchant_id,
                merchant_name=merchant_name,
                final_price_yuan=fen_to_yuan(record.total_amount),
                transaction_id=transaction_id,
            )
            bill.status = SplitBillStatus.SUBMITTED
            bill.settled_at = time.time()
            record.status = EscrowStatus.SETTLED
            record.unfrozen_at = time.time()
            record.split_bill_id = bill.bill_id
            record._add_audit(
                "SETTLE",
                f"分账：商家 ¥{fen_to_yuan(bill.merchant_amount)}，"
                f"平台 ¥{fen_to_yuan(bill.platform_fee)}"
            )
        return bill

    def refund(self, escrow_id, reason="交易取消") -> EscrowRecord:
        """解冻退回消费者"""
        with self._lock:
            record = self._get_or_raise(escrow_id)
            if record.status not in (EscrowStatus.FROZEN, EscrowStatus.PENDING):
                raise ValueError(f"[Escrow] {escrow_id} 状态={record.status}，仅FROZEN/PENDING可退款")
            record.status = EscrowStatus.REFUNDED
            record.unfrozen_at = time.time()
            record.failure_reason = reason
            record._add_audit("REFUND", f"退款原因：{reason}")
        return record

    def mark_failed(self, escrow_id, reason) -> EscrowRecord:
        with self._lock:
            record = self._get_or_raise(escrow_id)
            record.status = EscrowStatus.FAILED
            record.failure_reason = reason
            record._add_audit("FAILED", reason)
        return record

    def get(self, escrow_id):
        return self._records.get(escrow_id)

    def get_by_intent(self, intent_id):
        return next((r for r in self._records.values() if r.intent_id == intent_id), None)

    def summary(self) -> dict:
        """资金统计摘要"""
        rs = list(self._records.values())
        settled_fen = sum(r.total_amount for r in rs if r.status == EscrowStatus.SETTLED)
        return {
            "total_records":        len(rs),
            "frozen_count":         sum(1 for r in rs if r.status == EscrowStatus.FROZEN),
            "settled_count":        sum(1 for r in rs if r.status == EscrowStatus.SETTLED),
            "refunded_count":       sum(1 for r in rs if r.status == EscrowStatus.REFUNDED),
            "failed_count":         sum(1 for r in rs if r.status == EscrowStatus.FAILED),
            "total_frozen_yuan":    fen_to_yuan(sum(r.total_amount for r in rs if r.status == EscrowStatus.FROZEN)),
            "total_settled_yuan":   fen_to_yuan(settled_fen),
            "total_refunded_yuan":  fen_to_yuan(sum(r.total_amount for r in rs if r.status == EscrowStatus.REFUNDED)),
            "platform_revenue_yuan":fen_to_yuan(round(settled_fen * PLATFORM_FEE_RATE)),
            "merchant_revenue_yuan":fen_to_yuan(round(settled_fen * MERCHANT_SHARE_RATE)),
            "fee_rate":             PLATFORM_FEE_RATE,
        }

    def _get_or_raise(self, escrow_id) -> EscrowRecord:
        r = self._records.get(escrow_id)
        if not r:
            raise KeyError(f"[Escrow] escrow_id={escrow_id} 不存在")
        return r


# ─── 全局单例 ─────────────────────────────────────────────
escrow_manager = EscrowManager()
