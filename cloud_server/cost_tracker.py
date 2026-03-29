"""Project Claw 成本追踪系统 - cloud_server/cost_tracker.py"""
import logging, json, time
from typing import Dict, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import sqlite3

logger = logging.getLogger(__name__)

@dataclass
class CostRecord:
    transaction_id: str
    tenant_id: str
    model_id: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float
    cost_cny: float
    timestamp: float
    query: str = ""

class CostTracker:
    """成本追踪系统"""
    
    def __init__(self, db_path: str = "./transaction_ledger.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """初始化数据库"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS cost_records (
                transaction_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                model_id TEXT NOT NULL,
                input_tokens INTEGER,
                output_tokens INTEGER,
                total_tokens INTEGER,
                cost_usd REAL,
                cost_cny REAL,
                timestamp REAL,
                query TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            
            cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tenant_id ON cost_records(tenant_id)
            """)
            
            cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp ON cost_records(timestamp)
            """)
            
            conn.commit()
            conn.close()
            logger.info("✓ 成本追踪数据库已初始化")
        except Exception as e:
            logger.error(f"初始化数据库失败: {e}")
    
    def record_cost(self, record: CostRecord) -> bool:
        """记录成本"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
            INSERT INTO cost_records 
            (transaction_id, tenant_id, model_id, input_tokens, output_tokens, total_tokens, cost_usd, cost_cny, timestamp, query)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.transaction_id,
                record.tenant_id,
                record.model_id,
                record.input_tokens,
                record.output_tokens,
                record.total_tokens,
                record.cost_usd,
                record.cost_cny,
                record.timestamp,
                record.query
            ))
            
            conn.commit()
            conn.close()
            
            logger.info(f"✓ 成本已记录: {record.transaction_id} (${record.cost_usd:.4f})")
            return True
        except Exception as e:
            logger.error(f"记录成本失败: {e}")
            return False
    
    def get_tenant_cost(self, tenant_id: str, start_time: Optional[float] = None, end_time: Optional[float] = None) -> Dict[str, Any]:
        """获取租户成本统计"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            query = "SELECT * FROM cost_records WHERE tenant_id = ?"
            params = [tenant_id]
            
            if start_time:
                query += " AND timestamp >= ?"
                params.append(start_time)
            
            if end_time:
                query += " AND timestamp <= ?"
                params.append(end_time)
            
            cursor.execute(query, params)
            records = cursor.fetchall()
            
            total_cost_usd = sum(r[6] for r in records)
            total_cost_cny = sum(r[7] for r in records)
            total_tokens = sum(r[5] for r in records)
            
            conn.close()
            
            return {
                "tenant_id": tenant_id,
                "total_cost_usd": total_cost_usd,
                "total_cost_cny": total_cost_cny,
                "total_tokens": total_tokens,
                "record_count": len(records),
                "avg_cost_per_request": total_cost_usd / len(records) if records else 0
            }
        except Exception as e:
            logger.error(f"获取租户成本失败: {e}")
            return {}
    
    def get_daily_cost(self, date: str) -> Dict[str, Any]:
        """获取每日成本统计"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 解析日期
            dt = datetime.strptime(date, "%Y-%m-%d")
            start_time = dt.timestamp()
            end_time = start_time + 86400
            
            cursor.execute("""
            SELECT tenant_id, SUM(cost_usd), SUM(cost_cny), SUM(total_tokens), COUNT(*)
            FROM cost_records
            WHERE timestamp >= ? AND timestamp < ?
            GROUP BY tenant_id
            """, (start_time, end_time))
            
            records = cursor.fetchall()
            conn.close()
            
            return {
                "date": date,
                "tenants": [
                    {
                        "tenant_id": r[0],
                        "cost_usd": r[1],
                        "cost_cny": r[2],
                        "total_tokens": r[3],
                        "request_count": r[4]
                    }
                    for r in records
                ]
            }
        except Exception as e:
            logger.error(f"获取每日成本失败: {e}")
            return {}
    
    def get_model_cost_breakdown(self, tenant_id: str) -> Dict[str, Any]:
        """获取模型成本分布"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
            SELECT model_id, SUM(cost_usd), SUM(cost_cny), SUM(total_tokens), COUNT(*)
            FROM cost_records
            WHERE tenant_id = ?
            GROUP BY model_id
            """, (tenant_id,))
            
            records = cursor.fetchall()
            conn.close()
            
            return {
                "tenant_id": tenant_id,
                "models": [
                    {
                        "model_id": r[0],
                        "cost_usd": r[1],
                        "cost_cny": r[2],
                        "total_tokens": r[3],
                        "request_count": r[4]
                    }
                    for r in records
                ]
            }
        except Exception as e:
            logger.error(f"获取模型成本分布失败: {e}")
            return {}

def usd_to_cny(usd: float, rate: float = 7.0) -> float:
    """USD 转 CNY"""
    return usd * rate
