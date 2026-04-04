"""
Project Claw v16.0 - edge_box/depin_miner.py
DePIN 算力共享守护：凌晨闲时模拟算力收益
"""
from __future__ import annotations

import logging
import random
import threading
import time
from datetime import datetime

logger = logging.getLogger("claw.edge.depin")


class DePINMiner:
    def __init__(self, start_hour: int = 2, end_hour: int = 6):
        self.start_hour = start_hour
        self.end_hour = end_hour
        self._stop = False
        self._thread: threading.Thread | None = None

    def _in_window(self) -> bool:
        h = datetime.now().hour
        return self.start_hour <= h < self.end_hour

    def _loop(self):
        while not self._stop:
            if self._in_window():
                earn = round(random.uniform(0.08, 0.22), 2)
                logger.info("[DePIN] 闲置 NPU 算力池启动... 当前收益 ¥%.2f", earn)
                time.sleep(30)
            else:
                time.sleep(60)

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop = False
        self._thread = threading.Thread(target=self._loop, daemon=True, name="DePINMiner")
        self._thread.start()

    def stop(self):
        self._stop = True
