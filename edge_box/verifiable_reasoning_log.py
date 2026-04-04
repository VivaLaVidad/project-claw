from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

import requests
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

logger = logging.getLogger("claw.edge.verifiable")


class VerifiableReasoningLogger:
    def __init__(self, db_path: str = "./audit.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

        device_source = (
            os.getenv("DEVICE_PHYSICAL_ID")
            or os.getenv("DEVICE_SERIAL")
            or str(uuid.getnode())
        )
        seed = hashlib.sha256(device_source.encode("utf-8")).digest()
        self._private_key = Ed25519PrivateKey.from_private_bytes(seed)

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.db_path, check_same_thread=False)
        c.row_factory = sqlite3.Row
        return c

    def _init_db(self) -> None:
        with self._conn() as c:
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS verifiable_reasoning_logs (
                    log_id TEXT PRIMARY KEY,
                    trade_id TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    signature_b64 TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    record_hash TEXT NOT NULL,
                    verify_code TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            c.execute("CREATE INDEX IF NOT EXISTS idx_vrl_trade_id ON verifiable_reasoning_logs(trade_id)")
            c.commit()

    def _last_hash(self) -> str:
        with self._conn() as c:
            row = c.execute(
                "SELECT record_hash FROM verifiable_reasoning_logs ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            return str(row[0]) if row else ("0" * 64)

    def log_trade_evidence(
        self,
        *,
        trade_id: str,
        current_bottom_price: float,
        llm_reasoning_step: str,
        original_customer_msg: str,
        final_offer: float,
    ) -> str:
        evidence = {
            "Current_Bottom_Price": current_bottom_price,
            "LLM_Reasoning_Step": llm_reasoning_step,
            "Original_Customer_Msg": original_customer_msg,
            "Final_Offer": final_offer,
        }

        evidence_json = json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        previous_hash = self._last_hash()
        sign_input = f"{previous_hash}|{trade_id}|{evidence_json}".encode("utf-8")

        signature = self._private_key.sign(sign_input)
        signature_b64 = base64.b64encode(signature).decode("ascii")

        record_hash = hashlib.sha256(f"{previous_hash}|{evidence_json}|{signature_b64}".encode("utf-8")).hexdigest()
        verify_code = hashlib.sha256(record_hash.encode("utf-8")).hexdigest()[:8].upper()
        log_id = str(uuid.uuid4())
        now = time.time()

        with self._conn() as c:
            c.execute(
                """
                INSERT INTO verifiable_reasoning_logs(
                    log_id, trade_id, evidence_json, signature_b64, previous_hash,
                    record_hash, verify_code, created_at
                ) VALUES(?,?,?,?,?,?,?,?)
                """,
                (log_id, trade_id, evidence_json, signature_b64, previous_hash, record_hash, verify_code, now),
            )
            c.commit()

        self._notify_feishu(trade_id=trade_id, verify_code=verify_code)
        logger.info("[VerifiableLog] trade=%s verify_code=%s", trade_id, verify_code)
        return verify_code

    @staticmethod
    def _notify_feishu(trade_id: str, verify_code: str) -> None:
        webhook = os.getenv("FEISHU_WEBHOOK_URL", "").strip()
        if not webhook:
            return
        text = f"交易审计校验码\ntrade_id={trade_id}\nverify_code={verify_code}"
        try:
            requests.post(webhook, json={"msg_type": "text", "content": {"text": text}}, timeout=5)
        except Exception as e:
            logger.warning("[VerifiableLog] feishu notify failed: %s", e)


_default_logger: VerifiableReasoningLogger | None = None


def get_reasoning_logger() -> VerifiableReasoningLogger:
    global _default_logger
    if _default_logger is None:
        _default_logger = VerifiableReasoningLogger(db_path=os.getenv("AUDIT_DB_PATH", "./audit.db"))
    return _default_logger
