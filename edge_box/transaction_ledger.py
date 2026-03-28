"""
edge_box/transaction_ledger.py
Project Claw - 防篡改交易账本（SQLite + SHA256 链式哈希）

设计目标：
- 所有交易状态流转记录在 SQLite 中，不可删除
- 每条记录包含 visual_proof_hash，防止伪造支付证明
- 链式哈希（prev_hash）确保记录顺序不可篡改
- 可审计：完整的状态机流转日志
"""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
import uuid
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
from threading import Lock
from typing import List, Optional

logger = logging.getLogger("claw.edge.ledger")

LEDGER_DB_PATH = Path("logs/transaction_ledger.db")


# ─── 枚举 ──────────────────────────────────────────────────────────────────
class TradeStatus(str, Enum):
    INITIATED        = "INITIATED"         # 收到 ExecuteTrade 信令
    QR_GENERATED     = "QR_GENERATED"      # 收款码已生成并发送
    POLLING          = "POLLING"           # 视觉轮询中
    PAYMENT_DETECTED = "PAYMENT_DETECTED"  # 视觉捕获到支付通知
    ACK_SENT         = "ACK_SENT"          # PAYMENT_SUCCESS_ACK 已发送
    TIMEOUT          = "TIMEOUT"           # 60s 超时，熔断回滚
    FAILED           = "FAILED"            # 其他失败


# ─── 数据模型 ───────────────────────────────────────────────────────────────
@dataclass
class LedgerEntry:
    entry_id:          str
    trade_id:          str
    intent_id:         str
    client_id:         str
    merchant_id:       str
    amount_yuan:       float
    status:            str
    visual_proof_hash: Optional[str]   # SHA256(screenshot_bytes)
    ocr_snippet:       Optional[str]   # 捕获到的 OCR 关键词
    prev_hash:         Optional[str]   # 上一条记录的 entry_hash（链式）
    entry_hash:        str             # 本条记录的 SHA256
    created_at:        float
    extra:             Optional[str]   # JSON 扩展字段


# ─── TransactionLedger ─────────────────────────────────────────────────────
class TransactionLedger:
    """
    防篡改交易账本。

    使用方式：
        ledger = TransactionLedger()
        entry  = ledger.initiate(trade_id, intent_id, client_id, merchant_id, 18.5)
        ledger.update(trade_id, TradeStatus.QR_GENERATED)
        ledger.update(trade_id, TradeStatus.PAYMENT_DETECTED,
                      visual_proof_hash="abc123", ocr_snippet="微信支付 ¥18.5")
    """

    def __init__(self, db_path: Path = LEDGER_DB_PATH) -> None:
        self._db_path = db_path
        self._lock    = Lock()
        self._init_db()

    def _init_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ledger (
                    entry_id          TEXT PRIMARY KEY,
                    trade_id          TEXT NOT NULL,
                    intent_id         TEXT NOT NULL,
                    client_id         TEXT NOT NULL,
                    merchant_id       TEXT NOT NULL,
                    amount_yuan       REAL NOT NULL,
                    status            TEXT NOT NULL,
                    visual_proof_hash TEXT,
                    ocr_snippet       TEXT,
                    prev_hash         TEXT,
                    entry_hash        TEXT NOT NULL,
                    created_at        REAL NOT NULL,
                    extra             TEXT
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_trade_id ON ledger(trade_id)"
            )
            conn.commit()
        logger.info(f"[Ledger] DB 已初始化: {self._db_path}")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self._db_path), check_same_thread=False)

    # ── 发起交易 ──
    def initiate(
        self,
        trade_id:    str,
        intent_id:   str,
        client_id:   str,
        merchant_id: str,
        amount_yuan: float,
        extra:       Optional[dict] = None,
    ) -> LedgerEntry:
        return self._append(
            trade_id    = trade_id,
            intent_id   = intent_id,
            client_id   = client_id,
            merchant_id = merchant_id,
            amount_yuan = amount_yuan,
            status      = TradeStatus.INITIATED,
            extra       = extra,
        )

    # ── 状态更新 ──
    def update(
        self,
        trade_id:          str,
        status:            TradeStatus,
        visual_proof_hash: Optional[str] = None,
        ocr_snippet:       Optional[str] = None,
        extra:             Optional[dict] = None,
    ) -> LedgerEntry:
        """
        追加一条新状态记录（不修改旧记录，只追加）。
        从上一条记录继承 intent_id / client_id / merchant_id / amount_yuan。
        """
        prev = self.latest(trade_id)
        if not prev:
            raise ValueError(f"[Ledger] trade_id={trade_id} 不存在，请先调用 initiate()")
        return self._append(
            trade_id          = trade_id,
            intent_id         = prev.intent_id,
            client_id         = prev.client_id,
            merchant_id       = prev.merchant_id,
            amount_yuan       = prev.amount_yuan,
            status            = status,
            visual_proof_hash = visual_proof_hash,
            ocr_snippet       = ocr_snippet,
            extra             = extra,
        )

    # ── 查询最新状态 ──
    def latest(self, trade_id: str) -> Optional[LedgerEntry]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM ledger WHERE trade_id=? ORDER BY created_at DESC LIMIT 1",
                (trade_id,),
            ).fetchone()
        return self._row_to_entry(row) if row else None

    # ── 查询完整流转历史 ──
    def history(self, trade_id: str) -> List[LedgerEntry]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM ledger WHERE trade_id=? ORDER BY created_at ASC",
                (trade_id,),
            ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    # ── 链式完整性校验 ──
    def verify_chain(self, trade_id: str) -> bool:
        """
        验证某笔交易的链式哈希完整性。
        任意一条记录被篡改都会导致校验失败。
        """
        entries = self.history(trade_id)
        for i, entry in enumerate(entries):
            expected = self._compute_hash(
                entry_id          = entry.entry_id,
                trade_id          = entry.trade_id,
                status            = entry.status,
                amount_yuan       = entry.amount_yuan,
                visual_proof_hash = entry.visual_proof_hash,
                prev_hash         = entry.prev_hash,
                created_at        = entry.created_at,
            )
            if expected != entry.entry_hash:
                logger.error(f"[Ledger] 链式校验失败: entry_id={entry.entry_id}")
                return False
        return True

    # ── 内部：追加记录 ──
    def _append(
        self,
        trade_id:          str,
        intent_id:         str,
        client_id:         str,
        merchant_id:       str,
        amount_yuan:       float,
        status:            TradeStatus,
        visual_proof_hash: Optional[str] = None,
        ocr_snippet:       Optional[str] = None,
        extra:             Optional[dict] = None,
    ) -> LedgerEntry:
        with self._lock:
            prev = self.latest(trade_id) if status != TradeStatus.INITIATED else None
            prev_hash  = prev.entry_hash if prev else None
            entry_id   = str(uuid.uuid4())
            created_at = time.time()
            entry_hash = self._compute_hash(
                entry_id=entry_id, trade_id=trade_id,
                status=status.value, amount_yuan=amount_yuan,
                visual_proof_hash=visual_proof_hash,
                prev_hash=prev_hash, created_at=created_at,
            )
            entry = LedgerEntry(
                entry_id=entry_id, trade_id=trade_id,
                intent_id=intent_id, client_id=client_id,
                merchant_id=merchant_id, amount_yuan=amount_yuan,
                status=status.value,
                visual_proof_hash=visual_proof_hash,
                ocr_snippet=ocr_snippet,
                prev_hash=prev_hash, entry_hash=entry_hash,
                created_at=created_at,
                extra=json.dumps(extra, ensure_ascii=False) if extra else None,
            )
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO ledger
                    (entry_id,trade_id,intent_id,client_id,merchant_id,
                     amount_yuan,status,visual_proof_hash,ocr_snippet,
                     prev_hash,entry_hash,created_at,extra)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        entry.entry_id, entry.trade_id, entry.intent_id,
                        entry.client_id, entry.merchant_id, entry.amount_yuan,
                        entry.status, entry.visual_proof_hash, entry.ocr_snippet,
                        entry.prev_hash, entry.entry_hash, entry.created_at, entry.extra,
                    ),
                )
                conn.commit()
            logger.info(
                f"[Ledger] trade={trade_id} status={status.value} "
                f"hash={entry_hash[:12]}..."
            )
        return entry

    @staticmethod
    def _compute_hash(
        entry_id: str, trade_id: str, status: str,
        amount_yuan: float, visual_proof_hash: Optional[str],
        prev_hash: Optional[str], created_at: float,
    ) -> str:
        payload = json.dumps({
            "entry_id":          entry_id,
            "trade_id":          trade_id,
            "status":            status,
            "amount_yuan":       amount_yuan,
            "visual_proof_hash": visual_proof_hash,
            "prev_hash":         prev_hash,
            "created_at":        created_at,
        }, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()

    @staticmethod
    def _row_to_entry(row: tuple) -> LedgerEntry:
        return LedgerEntry(
            entry_id=row[0], trade_id=row[1], intent_id=row[2],
            client_id=row[3], merchant_id=row[4], amount_yuan=row[5],
            status=row[6], visual_proof_hash=row[7], ocr_snippet=row[8],
            prev_hash=row[9], entry_hash=row[10], created_at=row[11],
            extra=row[12],
        )


# ─── 全局单例 ─────────────────────────────────────────────────────────────────
transaction_ledger = TransactionLedger()
