"""
Project Claw v16.1 - edge_box/vla_driver.py
VLA 视觉动作驱动：截图 -> 视觉规划 -> 贝塞尔轨迹触控 -> 视觉 ACK
"""
from __future__ import annotations

import base64
import logging
import math
import random
import re
import time
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger("claw.edge.vla")


@dataclass
class VLAAction:
    action: str
    x: float
    y: float
    text: str = ""
    confidence: float = 0.8


class VLADriver:
    """轻量 VLA 驱动，兼容现有 PhysicalTool。"""

    def __init__(
        self,
        capture_b64_fn: Callable[[], str],
        tap_fn: Callable[[float, float], None],
        input_text_fn: Callable[[str], None],
        enter_fn: Callable[[], None],
        detect_text_fn: Callable[[], str],
    ):
        self.capture_b64_fn = capture_b64_fn
        self.tap_fn = tap_fn
        self.input_text_fn = input_text_fn
        self.enter_fn = enter_fn
        self.detect_text_fn = detect_text_fn

    def infer_action(self, instruction: str, fallback_x: float, fallback_y: float) -> VLAAction:
        """
        2026 VLA 接口预留：
        - 当前采用稳定启发式 + 可落地动作输出
        - 后续可直接替换为 OmniParser/Qwen-VL GUI grounding 结果
        """
        text = (instruction or "").strip()
        if not text:
            return VLAAction(action="tap", x=fallback_x, y=fallback_y, confidence=0.5)

        # 轻量可控策略：输入类指令优先输出 type
        if any(k in text for k in ["发送", "回复", "输入", "说"]):
            return VLAAction(action="type", x=fallback_x, y=fallback_y, text=text, confidence=0.9)

        return VLAAction(action="tap", x=fallback_x, y=fallback_y, confidence=0.7)

    def _bezier_points(self, x0: float, y0: float, x1: float, y1: float, n: int = 12):
        cx = (x0 + x1) / 2 + random.uniform(-20, 20)
        cy = (y0 + y1) / 2 + random.uniform(-20, 20)
        pts = []
        for i in range(n):
            t = i / max(1, (n - 1))
            bx = (1 - t) * (1 - t) * x0 + 2 * (1 - t) * t * cx + t * t * x1
            by = (1 - t) * (1 - t) * y0 + 2 * (1 - t) * t * cy + t * t * y1
            pts.append((bx, by))
        return pts

    def execute_action(self, action: VLAAction, start_x: float = 540.0, start_y: float = 1800.0) -> bool:
        try:
            if action.action == "type":
                # 贝塞尔轨迹 + jitter 点击输入框
                for x, y in self._bezier_points(start_x, start_y, action.x, action.y):
                    self.tap_fn(x + random.uniform(-1.5, 1.5), y + random.uniform(-1.5, 1.5))
                    time.sleep(0.01)
                self.tap_fn(action.x, action.y)
                time.sleep(0.15)
                self.input_text_fn(action.text)
                time.sleep(0.1)
                self.enter_fn()
                return True

            if action.action == "tap":
                for x, y in self._bezier_points(start_x, start_y, action.x, action.y, n=10):
                    self.tap_fn(x + random.uniform(-1.0, 1.0), y + random.uniform(-1.0, 1.0))
                    time.sleep(0.01)
                self.tap_fn(action.x, action.y)
                return True

            return False
        except Exception as e:
            logger.warning("[VLA] execute failed: %s", e)
            return False

    def wait_visual_ack(self, amount_yuan: float, timeout_sec: int = 60, poll_interval: float = 2.0) -> bool:
        """视觉核销：轮询直到屏幕出现微信收款成功文案。"""
        deadline = time.time() + timeout_sec
        amount_int = int(round(float(amount_yuan)))
        amount_pattern = re.compile(rf"(收款|到账|微信支付收款).{{0,8}}{amount_int}")

        while time.time() < deadline:
            txt = (self.detect_text_fn() or "").replace("\n", " ")
            if txt:
                if "微信支付" in txt and ("收款" in txt or "到账" in txt):
                    if amount_pattern.search(txt) or str(amount_int) in txt:
                        logger.info("[VLA] visual ack success amount=%s", amount_int)
                        return True
            time.sleep(poll_interval)

        logger.warning("[VLA] visual ack timeout amount=%s", amount_int)
        return False

    @staticmethod
    def png_bytes_to_b64(png: bytes) -> str:
        return base64.b64encode(png).decode("utf-8")
