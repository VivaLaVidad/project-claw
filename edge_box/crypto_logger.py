"""
crypto_logger.py - 不可篡改审计追踪系统（第一部分）
"""

import hashlib
import json
import sqlite3
import time
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from pathlib import Path
import threading
from enum import Enum


class EventType(str, Enum):
    TRADE_EXECUTE = "TRADE_EXECUTE"
    PHYSICAL_ACTION = "PHYSICAL_ACTION"
    PAYMENT_VERIFY = "PAYMENT_VERIFY"
    OVERRIDE_COMMAND = "OVERRIDE_COMMAND"
    SYSTEM_ERROR = "SYSTEM_ERROR"


@dataclass
class AuditEvent:
    event_id: str
    event_type: EventType
    timestamp: float
    intent_id: str
    merchant_id: str
    client_id: str
    price: float
    action: str
    details: Dict[str, Any]
    previous_hash: str
    event_hash: str = ""
    signature: str = ""


class CryptoLogger:
    """不可篡改的审计追踪系统 - 区块链式链式签名"""
    
    def __init__(self, db_path: str = "./audit.db", secret_key: str = None):
        self.db_path = Path(db_path)
        self.secret_key = secret_key or "claw-audit-secret-key"
        self.lock = threading.RLock()
        self._init_database()
        self.last_hash = self._get_last_event_hash()
    
    def _init_database(self):
        """初始化审计数据库"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    intent_id TEXT NOT NULL,
                    merchant_id TEXT NOT NULL,
                    client_id TEXT NOT NULL,
                    price REAL NOT NULL,
                    action TEXT NOT NULL,
                    details TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL,
                    signature TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_timestamp (timestamp),
                    INDEX idx_intent_id (intent_id),
                    INDEX idx_merchant_id (merchant_id)
                )
            """)
            conn.commit()
    
    def _calculate_event_hash(self, event: AuditEvent) -> str:
        """计算事件的 SHA-256 哈希（链式签名）"""
        hash_input = {
            'timestamp': event.timestamp,
            'intent_id': event.intent_id,
            'merchant_id': event.merchant_id,
            'client_id': event.client_id,
            'price': event.price,
            'action': event.action,
            'previous_hash': event.previous_hash,
        }
        hash_string = json.dumps(hash_input, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(hash_string.encode()).hexdigest()
    
    def _calculate_signature(self, event_hash: str) -> str:
        """计算 HMAC 签名"""
        import hmac
        return hmac.new(
            self.secret_key.encode(),
            event_hash.encode(),
            hashlib.sha256
        ).hexdigest()
    
    def _get_last_event_hash(self) -> str:
        """获取最后一个事件的哈希"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT event_hash FROM audit_events ORDER BY timestamp DESC LIMIT 1"
                )
                result = cursor.fetchone()
                return result[0] if result else "0" * 64
        except:
            return "0" * 64
    
    def log_trade_execute(
        self,
        intent_id: str,
        merchant_id: str,
        client_id: str,
        price: float,
        action: str,
        details: Dict[str, Any] = None,
    ) -> str:
        """记录交易执行事件"""
        return self._log_event(
            EventType.TRADE_EXECUTE,
            intent_id, merchant_id, client_id, price, action,
            details or {}
        )
    
    def log_physical_action(
        self,
        intent_id: str,
        merchant_id: str,
        client_id: str,
        price: float,
        action: str,
        details: Dict[str, Any] = None,
    ) -> str:
        """记录物理操作事件（微信发送、支付验证）"""
        return self._log_event(
            EventType.PHYSICAL_ACTION,
            intent_id, merchant_id, client_id, price, action,
            details or {}
        )
    
    def log_override_command(
        self,
        merchant_id: str,
        command: str,
        reason: str = "",
        details: Dict[str, Any] = None,
    ) -> str:
        """记录手动覆盖命令"""
        return self._log_event(
            EventType.OVERRIDE_COMMAND,
            "N/A", merchant_id, "N/A", 0.0, command,
            {'reason': reason, 'timestamp': time.time(), **(details or {})}
        )
    
    def _log_event(
        self,
        event_type: EventType,
        intent_id: str,
        merchant_id: str,
        client_id: str,
        price: float,
        action: str,
        details: Dict[str, Any],
    ) -> str:
        """内部方法：记录审计事件"""
        with self.lock:
            try:
                event_id = f"{merchant_id}_{intent_id}_{int(time.time() * 1000)}"
                
                event = AuditEvent(
                    event_id=event_id,
                    event_type=event_type,
                    timestamp=time.time(),
                    intent_id=intent_id,
                    merchant_id=merchant_id,
                    client_id=client_id,
                    price=price,
                    action=action,
                    details=details,
                    previous_hash=self.last_hash,
                )
                
                event.event_hash = self._calculate_event_hash(event)
                event.signature = self._calculate_signature(event.event_hash)
                
                self._store_event(event)
                self.last_hash = event.event_hash
                
                return event_id
            except Exception as e:
                print(f"Error logging event: {e}")
                raise
    
    def _store_event(self, event: AuditEvent):
        """将事件存储到数据库"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO audit_events (
                    event_id, event_type, timestamp, intent_id, merchant_id,
                    client_id, price, action, details, previous_hash,
                    event_hash, signature
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event.event_id,
                event.event_type.value,
                event.timestamp,
                event.intent_id,
                event.merchant_id,
                event.client_id,
                event.price,
                event.action,
                json.dumps(event.details),
                event.previous_hash,
                event.event_hash,
                event.signature,
            ))
            conn.commit()
    
    def verify_audit_trail(self) -> bool:
        """验证审计追踪的完整性"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT event_hash, previous_hash, signature FROM audit_events ORDER BY timestamp"
            )
            
            previous_hash = "0" * 64
            
            for row in cursor:
                event_hash, stored_previous_hash, signature = row
                
                if stored_previous_hash != previous_hash:
                    return False
                
                expected_signature = self._calculate_signature(event_hash)
                if signature != expected_signature:
                    return False
                
                previous_hash = event_hash
        
        return True
    
    def export_audit_report(
        self,
        merchant_id: str,
        start_time: float = None,
        end_time: float = None,
    ) -> Dict[str, Any]:
        """导出审计报告（用于合规审查）"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            query = "SELECT * FROM audit_events WHERE merchant_id = ?"
            params = [merchant_id]
            
            if start_time:
                query += " AND timestamp >= ?"
                params.append(start_time)
            
            if end_time:
                query += " AND timestamp <= ?"
                params.append(end_time)
            
            query += " ORDER BY timestamp"
            
            cursor = conn.execute(query, params)
            events = [dict(row) for row in cursor.fetchall()]
        
        report = {
            'merchant_id': merchant_id,
            'report_time': datetime.now().isoformat(),
            'total_events': len(events),
            'audit_trail_verified': self.verify_audit_trail(),
            'events': events,
            'summary': {
                'total_trades': sum(1 for e in events if e['event_type'] == 'TRADE_EXECUTE'),
                'total_amount': sum(e['price'] for e in events if e['event_type'] == 'TRADE_EXECUTE'),
                'total_actions': sum(1 for e in events if e['event_type'] == 'PHYSICAL_ACTION'),
                'override_commands': sum(1 for e in events if e['event_type'] == 'OVERRIDE_COMMAND'),
            }
        }
        
        return report
    
    def get_event_chain(self, intent_id: str) -> List[Dict[str, Any]]:
        """获取特定意图的完整事件链"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM audit_events WHERE intent_id = ? ORDER BY timestamp",
                (intent_id,)
            )
            return [dict(row) for row in cursor.fetchall()]


_crypto_logger: Optional[CryptoLogger] = None

def get_crypto_logger() -> CryptoLogger:
    global _crypto_logger
    if _crypto_logger is None:
        _crypto_logger = CryptoLogger()
    return _crypto_logger

def init_crypto_logger(db_path: str = "./audit.db", secret_key: str = None):
    global _crypto_logger
    _crypto_logger = CryptoLogger(db_path=db_path, secret_key=secret_key)
