"""edge_box/physical_tool.py
设备物理注入工具（依赖倒置 + EasyOCR 视觉接管）

低资源策略：
- 不加载本地大模型权重（transformers/vLLM）
- 视觉识别使用 EasyOCR(gpu=True)
- 每次视觉调用后尝试 torch.cuda.empty_cache() 释放显存
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import numpy as np
from PIL import Image

try:
    import easyocr
except Exception:  # pragma: no cover
    easyocr = None

try:
    import torch
except Exception:  # pragma: no cover
    torch = None

logger = logging.getLogger(__name__)


@dataclass
class TapTarget:
    element_name: str
    x: int
    y: int
    confidence: float


class BaseDeviceDriver(ABC):
    @abstractmethod
    async def capture_screen(self) -> Image.Image:
        ...

    @abstractmethod
    async def tap_element(self, element_name: str) -> bool:
        ...

    @abstractmethod
    async def type_text(self, text: str) -> bool:
        ...


def generate_bezier_curve(start: tuple[int, int], end: tuple[int, int], steps: int = 20) -> list[tuple[int, int]]:
    x0, y0 = start
    x3, y3 = end
    dx, dy = x3 - x0, y3 - y0
    c1 = (x0 + int(dx * 0.3) + random.randint(-20, 20), y0 + int(dy * 0.2) + random.randint(-20, 20))
    c2 = (x0 + int(dx * 0.7) + random.randint(-20, 20), y0 + int(dy * 0.8) + random.randint(-20, 20))

    pts: list[tuple[int, int]] = []
    for i in range(max(2, steps)):
        t = i / (steps - 1)
        x = (1 - t) ** 3 * x0 + 3 * (1 - t) ** 2 * t * c1[0] + 3 * (1 - t) * t**2 * c2[0] + t**3 * x3
        y = (1 - t) ** 3 * y0 + 3 * (1 - t) ** 2 * t * c1[1] + 3 * (1 - t) * t**2 * c2[1] + t**3 * y3
        pts.append((int(x), int(y)))
    return pts


class OCR_Android_Driver(BaseDeviceDriver):
    def __init__(self, device_id: Optional[str] = None):
        self.device_id = device_id or os.getenv("ANDROID_DEVICE_ID", "")
        self._ocr = None

    def _adb_prefix(self) -> list[str]:
        cmd = ["adb"]
        if self.device_id:
            cmd += ["-s", self.device_id]
        return cmd

    async def _run_adb(self, args: list[str]) -> bytes:
        cmd = self._adb_prefix() + args
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"adb failed: {' '.join(cmd)} | {err.decode(errors='ignore')}")
        return out

    def _ensure_ocr(self):
        if self._ocr is not None:
            return self._ocr
        if easyocr is None:
            raise RuntimeError("easyocr_not_installed")
        # 低配机器允许走 GPU，若驱动不可用 EasyOCR 会自动回退
        self._ocr = easyocr.Reader(["ch_sim", "en"], gpu=True)
        return self._ocr

    async def capture_screen(self) -> Image.Image:
        raw = await self._run_adb(["exec-out", "screencap", "-p"])
        return Image.open(io.BytesIO(raw)).convert("RGB")

    async def _locate_element_with_ocr(self, element_name: str, image: Image.Image) -> TapTarget:
        ocr = self._ensure_ocr()
        aliases = {
            "发送收款码": ["发送收款码", "收款码", "发送", "send"],
            "输入框": ["输入", "请输入", "message"],
            "发送": ["发送", "send"],
        }
        keys = aliases.get(element_name, [element_name])

        arr = np.array(image)
        try:
            results = await asyncio.to_thread(ocr.readtext, arr)
        finally:
            if torch is not None and torch.cuda.is_available():
                try:
                    torch.cuda.empty_cache()
                except Exception:
                    pass

        best: Optional[TapTarget] = None
        for bbox, text, conf in results:
            txt = str(text).lower()
            if not any(k.lower() in txt for k in keys):
                continue
            x = int((bbox[0][0] + bbox[2][0]) / 2)
            y = int((bbox[0][1] + bbox[2][1]) / 2)
            cand = TapTarget(element_name=element_name, x=x, y=y, confidence=float(conf))
            if best is None or cand.confidence > best.confidence:
                best = cand

        if best is not None:
            return best

        # 找不到文字时兜底：按输入框/发送按钮经验位
        if element_name == "输入框":
            return TapTarget(element_name=element_name, x=image.width // 2, y=int(image.height * 0.92), confidence=0.1)
        return TapTarget(element_name=element_name, x=int(image.width * 0.92), y=int(image.height * 0.92), confidence=0.05)

    async def _inject_tap(self, x: int, y: int) -> bool:
        start = (x + random.randint(-60, 60), y + random.randint(-60, 60))
        pts = generate_bezier_curve(start, (x, y), steps=8)

        for i in range(len(pts) - 1):
            (x1, y1), (x2, y2) = pts[i], pts[i + 1]
            dur_ms = random.randint(18, 35)
            await self._run_adb(["shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(dur_ms)])
            await asyncio.sleep(random.uniform(0.006, 0.018))

        await asyncio.sleep(random.uniform(0.008, 0.028))
        await self._run_adb(["shell", "input", "tap", str(x), str(y)])
        return True

    async def tap_element(self, element_name: str) -> bool:
        image = await self.capture_screen()
        target = await self._locate_element_with_ocr(element_name, image)
        if target.confidence < 0.15:
            logger.warning("low confidence target for %s: %s", element_name, target)
        return await self._inject_tap(target.x, target.y)

    async def type_text(self, text: str) -> bool:
        await self.tap_element("输入框")
        await asyncio.sleep(random.uniform(0.05, 0.12))
        safe = text.replace(" ", "%s")
        chunks = [safe[i : i + 8] for i in range(0, len(safe), 8)]
        for chunk in chunks:
            await self._run_adb(["shell", "input", "text", chunk])
            await asyncio.sleep(random.uniform(0.012, 0.055))
        return True


_driver: Optional[BaseDeviceDriver] = None


def get_driver() -> BaseDeviceDriver:
    global _driver
    if _driver is None:
        _driver = OCR_Android_Driver()
    return _driver


async def analyze_screen() -> dict:
    drv = get_driver()
    img = await drv.capture_screen()
    return {"width": img.width, "height": img.height}


async def click_at(x: int, y: int) -> bool:
    drv = get_driver()
    if isinstance(drv, OCR_Android_Driver):
        return await drv._inject_tap(x, y)
    return False
