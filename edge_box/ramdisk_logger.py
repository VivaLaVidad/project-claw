"""
ramdisk_logger.py - 内存盘保护策略
防止高频日志烧毁 eMMC 闪存颗粒
"""

import os
import json
import time
from pathlib import Path
from typing import Optional
from datetime import datetime


class RAMDiskLogger:
    """内存盘日志系统 - 保护 eMMC"""
    
    def __init__(self, ramdisk_path: str = "/dev/shm"):
        """
        初始化内存盘日志
        
        Args:
            ramdisk_path: 内存盘路径（Linux: /dev/shm, Windows: 使用内存缓冲）
        """
        self.ramdisk_path = Path(ramdisk_path)
        self.log_buffer = []
        self.buffer_size = 1000  # 缓冲 1000 条日志后写入
        self.max_file_size = 10 * 1024 * 1024  # 10MB
        
        # 创建日志目录
        self.log_dir = self.ramdisk_path / "claw_logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self.current_log_file = self._get_current_log_file()
    
    def _get_current_log_file(self) -> Path:
        """获取当前日志文件"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return self.log_dir / f"heartbeat_{timestamp}.jsonl"
    
    def log_heartbeat(self, data: dict):
        """
        记录心跳日志（高频操作）
        
        这些日志只存储在内存盘中，不会写入 eMMC
        """
        log_entry = {
            'timestamp': time.time(),
            'type': 'heartbeat',
            'data': data,
        }
        
        self.log_buffer.append(log_entry)
        
        # 缓冲满时写入内存盘
        if len(self.log_buffer) >= self.buffer_size:
            self._flush_to_ramdisk()
    
    def _flush_to_ramdisk(self):
        """将缓冲的日志写入内存盘"""
        if not self.log_buffer:
            return
        
        try:
            # 检查文件大小
            if self.current_log_file.exists():
                if self.current_log_file.stat().st_size > self.max_file_size:
                    self.current_log_file = self._get_current_log_file()
            
            # 追加写入
            with open(self.current_log_file, 'a') as f:
                for entry in self.log_buffer:
                    f.write(json.dumps(entry) + '\n')
            
            self.log_buffer.clear()
        
        except Exception as e:
            print(f"Error flushing to ramdisk: {e}")
    
    def log_ui_scan(self, scan_data: dict):
        """记录 UI 扫描心跳（高频）"""
        self.log_heartbeat({
            'type': 'ui_scan',
            'data': scan_data,
        })
    
    def log_connection_check(self, status: str):
        """记录连接检查心跳"""
        self.log_heartbeat({
            'type': 'connection_check',
            'status': status,
        })
    
    def cleanup_old_logs(self, keep_hours: int = 1):
        """清理旧日志（防止内存盘满）"""
        current_time = time.time()
        cutoff_time = current_time - (keep_hours * 3600)
        
        for log_file in self.log_dir.glob("*.jsonl"):
            if log_file.stat().st_mtime < cutoff_time:
                log_file.unlink()


_ramdisk_logger: Optional[RAMDiskLogger] = None

def get_ramdisk_logger() -> RAMDiskLogger:
    global _ramdisk_logger
    if _ramdisk_logger is None:
        _ramdisk_logger = RAMDiskLogger()
    return _ramdisk_logger
