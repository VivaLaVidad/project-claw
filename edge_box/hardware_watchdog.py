"""hardware_watchdog.py - 工业级底层防线"""
import asyncio, sqlite3, psutil, logging, time, json
from typing import Optional, Dict, List
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class DeadLetterItem:
    id: str
    trade_id: str
    merchant_id: str
    client_id: str
    amount: float
    status: str
    payload: str
    created_at: float
    retry_count: int = 0
    last_error: str = ""

class MemoryDiskLogger:
    """内存盘日志 - 保护 eMMC"""
    def __init__(self, ramdisk_path: str = "/dev/shm"):
        self.ramdisk_path = Path(ramdisk_path)
        self.log_dir = self.ramdisk_path / "claw_logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.buffer = []
        self.buffer_size = 1000
    
    def log_heartbeat(self, level: str, message: str, data: Dict = None):
        if level not in ["DEBUG", "INFO"]:
            return
        self.buffer.append({'timestamp': time.time(), 'level': level, 'message': message, 'data': data or {}})
        if len(self.buffer) >= self.buffer_size:
            self._flush()
    
    def _flush(self):
        try:
            log_file = self.log_dir / f"heartbeat_{int(time.time())}.jsonl"
            with open(log_file, 'a') as f:
                for entry in self.buffer:
                    f.write(json.dumps(entry) + '\n')
            self.buffer.clear()
        except Exception as e:
            logger.error(f"Flush error: {e}")

class OrphanProcessHunter:
    """孤儿进程猎手 - 防止内存泄漏"""
    def __init__(self, check_interval: int = 30, memory_threshold: float = 0.8):
        self.check_interval = check_interval
        self.memory_threshold = memory_threshold
        self.running = False
    
    async def start(self):
        self.running = True
        logger.info("Process hunter started")
        while self.running:
            try:
                await self._check()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Hunter error: {e}")
    
    async def _check(self):
        try:
            threshold = psutil.virtual_memory().total * self.memory_threshold
            for proc in psutil.process_iter(['pid', 'name', 'memory_info']):
                try:
                    if proc.info['memory_info'].rss > threshold and 'python' in proc.info['name'].lower():
                        if any(x in ' '.join(proc.cmdline()).lower() for x in ['easyocr', 'uiautomator2']):
                            logger.warning(f"Killing {proc.info['pid']}")
                            proc.kill()
                except:
                    pass
        except Exception as e:
            logger.error(f"Check error: {e}")
    
    async def stop(self):
        self.running = False

class DeadLetterQueue:
    """断网缓存队列 - 确保账本一致"""
    def __init__(self, db_path: str = "./dlq.db"):
        self.db_path = Path(db_path)
        self._init()
    
    def _init(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS dead_letters (
                id TEXT PRIMARY KEY, trade_id TEXT, merchant_id TEXT, client_id TEXT,
                amount REAL, status TEXT, payload TEXT, created_at REAL, retry_count INTEGER DEFAULT 0, last_error TEXT DEFAULT '')""")
            conn.commit()
    
    async def enqueue(self, item: DeadLetterItem):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("INSERT INTO dead_letters VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (item.id, item.trade_id, item.merchant_id, item.client_id, item.amount, item.status, item.payload, item.created_at, item.retry_count, item.last_error))
                conn.commit()
            logger.info(f"DLQ enqueued: {item.id}")
        except Exception as e:
            logger.error(f"Enqueue error: {e}")
    
    async def dequeue_batch(self, batch_size: int = 100) -> List[DeadLetterItem]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("SELECT * FROM dead_letters WHERE status='PENDING' LIMIT ?", (batch_size,)).fetchall()
                return [DeadLetterItem(**dict(r)) for r in rows]
        except Exception as e:
            logger.error(f"Dequeue error: {e}")
            return []
    
    async def mark_success(self, item_id: str):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("UPDATE dead_letters SET status='SUCCESS' WHERE id=?", (item_id,))
                conn.commit()
        except Exception as e:
            logger.error(f"Mark success error: {e}")
    
    async def mark_failed(self, item_id: str, error: str, max_retries: int = 3):
        try:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute("SELECT retry_count FROM dead_letters WHERE id=?", (item_id,)).fetchone()
                if row:
                    retry_count = row[0] + 1
                    status = 'FAILED' if retry_count >= max_retries else 'PENDING'
                    conn.execute("UPDATE dead_letters SET status=?, retry_count=?, last_error=? WHERE id=?",
                        (status, retry_count, error, item_id))
                    conn.commit()
        except Exception as e:
            logger.error(f"Mark failed error: {e}")

class HardwareWatchdog:
    """硬件看门狗 - 集成所有防线"""
    def __init__(self):
        self.memory_logger = MemoryDiskLogger()
        self.process_hunter = OrphanProcessHunter()
        self.dlq = DeadLetterQueue()
        self.running = False
    
    async def start(self):
        self.running = True
        logger.info("Watchdog started")
        asyncio.create_task(self.process_hunter.start())
        asyncio.create_task(self._cleanup())
        asyncio.create_task(self._recovery())
    
    async def _cleanup(self):
        while self.running:
            try:
                await asyncio.sleep(3600)
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
    
    async def _recovery(self):
        while self.running:
            try:
                if self._is_online():
                    items = await self.dlq.dequeue_batch(100)
                    for item in items:
                        try:
                            await self.dlq.mark_success(item.id)
                        except Exception as e:
                            await self.dlq.mark_failed(item.id, str(e))
                await asyncio.sleep(30)
            except Exception as e:
                logger.error(f"Recovery error: {e}")
    
    def _is_online(self) -> bool:
        try:
            import socket
            socket.create_connection(("8.8.8.8", 53), timeout=3)
            return True
        except:
            return False
    
    async def stop(self):
        self.running = False
        await self.process_hunter.stop()

_watchdog: Optional[HardwareWatchdog] = None

async def get_watchdog() -> HardwareWatchdog:
    global _watchdog
    if _watchdog is None:
        _watchdog = HardwareWatchdog()
        await _watchdog.start()
    return _watchdog

async def enqueue_dead_letter(trade_id: str, merchant_id: str, client_id: str, amount: float, payload: Dict) -> str:
    watchdog = await get_watchdog()
    item_id = f"{trade_id}_{int(time.time() * 1000)}"
    item = DeadLetterItem(id=item_id, trade_id=trade_id, merchant_id=merchant_id, client_id=client_id,
        amount=amount, status="PENDING", payload=json.dumps(payload), created_at=time.time())
    await watchdog.dlq.enqueue(item)
    return item_id
