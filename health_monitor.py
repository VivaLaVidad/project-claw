"""
Project Claw v13.0 - health_monitor.py
设备端自愈看门狗

功能：
  - 设备连接断开自动重连（指数退避）
  - OCR 引擎崩溃自动重启
  - 主循环卡死检测（心跳超时）
  - 磁盘空间检查
  - 结构化健康报告
"""
from __future__ import annotations

import logging
import os
import shutil
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger("claw.health")


@dataclass
class HealthStatus:
    device_ok:      bool  = False
    ocr_ok:         bool  = False
    disk_ok:        bool  = True
    loop_alive:     bool  = True
    last_heartbeat: float = field(default_factory=time.time)
    reconnect_count: int  = 0
    ocr_restart_count: int = 0
    errors:         list  = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "device_ok":      self.device_ok,
            "ocr_ok":         self.ocr_ok,
            "disk_ok":        self.disk_ok,
            "loop_alive":     self.loop_alive,
            "last_heartbeat": self.last_heartbeat,
            "reconnect_count": self.reconnect_count,
            "ocr_restart_count": self.ocr_restart_count,
            "errors":         self.errors[-10:],   # 最近10条
        }


class HealthMonitor:
    """
    自愈看门狗

    用法：
        monitor = HealthMonitor(
            reconnect_fn=lambda: u2.connect(),
            restart_ocr_fn=init_ocr,
        )
        monitor.start()
        # 主循环里定期调用：
        monitor.heartbeat()
    """

    HEARTBEAT_TIMEOUT = 30.0   # 秒：超过此时间没有心跳视为卡死
    DISK_MIN_MB       = 200    # 最少剩余磁盘空间
    RECONNECT_DELAYS  = [2, 4, 8, 16, 30, 60]  # 指数退避（秒）

    def __init__(
        self,
        reconnect_fn:   Callable,
        restart_ocr_fn: Callable,
        check_interval: float = 10.0,
        work_dir:       str   = ".",
    ):
        self.reconnect_fn   = reconnect_fn
        self.restart_ocr_fn = restart_ocr_fn
        self.check_interval = check_interval
        self.work_dir       = work_dir
        self.status         = HealthStatus()
        self._stop_event    = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self):
        self._thread = threading.Thread(
            target=self._loop,
            daemon=True,
            name="HealthMonitor",
        )
        self._thread.start()
        logger.info("[HealthMonitor] 看门狗启动")

    def stop(self):
        self._stop_event.set()

    def heartbeat(self):
        """主循环每次迭代调用，证明主循环仍在运行"""
        self.status.last_heartbeat = time.time()
        self.status.loop_alive     = True

    def mark_device_ok(self, ok: bool):
        self.status.device_ok = ok

    def mark_ocr_ok(self, ok: bool):
        self.status.ocr_ok = ok

    def get_status(self) -> dict:
        return self.status.to_dict()

    # ==================== 内部逻辑 ====================

    def _loop(self):
        while not self._stop_event.is_set():
            try:
                self._check_heartbeat()
                self._check_disk()
            except Exception as e:
                logger.error(f"[HealthMonitor] 检查异常: {e}")
            time.sleep(self.check_interval)

    def _check_heartbeat(self):
        elapsed = time.time() - self.status.last_heartbeat
        if elapsed > self.HEARTBEAT_TIMEOUT:
            self.status.loop_alive = False
            msg = f"主循环心跳超时 {elapsed:.0f}s"
            logger.error(f"[HealthMonitor] ❌ {msg}")
            self._record_error(msg)

    def _check_disk(self):
        try:
            free_mb = shutil.disk_usage(self.work_dir).free / 1024 / 1024
            if free_mb < self.DISK_MIN_MB:
                self.status.disk_ok = False
                msg = f"磁盘空间不足 {free_mb:.0f}MB"
                logger.warning(f"[HealthMonitor] ⚠️ {msg}")
                self._record_error(msg)
                self._cleanup_old_screenshots()
            else:
                self.status.disk_ok = True
        except Exception as e:
            logger.warning(f"[HealthMonitor] 磁盘检查失败: {e}")

    def _cleanup_old_screenshots(self):
        """清理截图文件释放磁盘空间"""
        for fname in ["current_screen.png", "chat_crop.png", "check_send.png"]:
            fpath = os.path.join(self.work_dir, fname)
            try:
                if os.path.exists(fpath):
                    os.remove(fpath)
            except Exception:
                pass
        logger.info("[HealthMonitor] 清理截图完成")

    def reconnect_device(self, device_factory: Optional[Callable] = None) -> Optional[object]:
        """带指数退避的设备重连"""
        factory = device_factory or self.reconnect_fn
        delays = self.RECONNECT_DELAYS
        for i, delay in enumerate(delays):
            try:
                logger.info(f"[HealthMonitor] 尝试重连设备 ({i+1}/{len(delays)})...")
                device = factory()
                self.status.device_ok = True
                self.status.reconnect_count += 1
                logger.info(f"[HealthMonitor] ✅ 设备重连成功")
                return device
            except Exception as e:
                logger.warning(f"[HealthMonitor] 重连失败: {e}，{delay}s 后重试")
                self._record_error(f"设备重连失败: {e}")
                time.sleep(delay)
        logger.error("[HealthMonitor] ❌ 设备重连彻底失败")
        return None

    def restart_ocr(self) -> bool:
        """重启 OCR 引擎"""
        try:
            logger.info("[HealthMonitor] 重启 OCR...")
            self.restart_ocr_fn()
            self.status.ocr_ok = True
            self.status.ocr_restart_count += 1
            logger.info("[HealthMonitor] ✅ OCR 重启成功")
            return True
        except Exception as e:
            logger.error(f"[HealthMonitor] OCR 重启失败: {e}")
            self._record_error(f"OCR 重启失败: {e}")
            return False

    def _record_error(self, msg: str):
        self.status.errors.append({"t": time.time(), "msg": msg})
        if len(self.status.errors) > 100:
            self.status.errors = self.status.errors[-50:]
