"""edge_box/physical_tool.py
设备物理注入工具（依赖倒置 + VLM 视觉接管）

说明：
- 该实现用于自动化测试与无障碍辅助，不用于绕过平台安全机制。
- 通过抽象驱动接口隔离具体设备能力，便于未来异构设备扩展。
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import os
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import httpx
from PIL import Image

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


def generate_bezier_curve(
    start: tuple[int, int],
    end: tuple[int, int],
    steps: int = 20,
) -> list[tuple[int, int]]:
    """生成三次贝塞尔轨迹点，模拟非线性手势轨迹。"""
    x0, y0 = start
    x3, y3 = end

    # 随机控制点：让轨迹有轻微弯曲
    dx = x3 - x0
    dy = y3 - y0
    c1 = (x0 + int(dx * 0.3) + random.randint(-20, 20), y0 + int(dy * 0.2) + random.randint(-20, 20))
    c2 = (x0 + int(dx * 0.7) + random.randint(-20, 20), y0 + int(dy * 0.8) + random.randint(-20, 20))

    pts: list[tuple[int, int]] = []
    for i in range(max(2, steps)):
        t = i / (steps - 1)
        x = (1 - t) ** 3 * x0 + 3 * (1 - t) ** 2 * t * c1[0] + 3 * (1 - t) * t**2 * c2[0] + t**3 * x3
        y = (1 - t) ** 3 * y0 + 3 * (1 - t) ** 2 * t * c1[1] + 3 * (1 - t) * t**2 * c2[1] + t**3 * y3
        pts.append((int(x), int(y)))
    return pts


class VLM_Android_Driver(BaseDeviceDriver):
    """通过 ADB + 本地 VLM 完成视觉定位和触控注入。"""

    def __init__(
        self,
        device_id: Optional[str] = None,
        vlm_base_url: Optional[str] = None,
        vlm_model: Optional[str] = None,
        timeout_sec: float = 10.0,
    ):
        self.device_id = device_id or os.getenv("ANDROID_DEVICE_ID", "")
        self.vlm_base_url = vlm_base_url or os.getenv("VLM_BASE_URL", "http://127.0.0.1:8000")
        self.vlm_model = vlm_model or os.getenv("VLM_MODEL", "Qwen-VL-Max")
        self.timeout_sec = timeout_sec

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

    async def capture_screen(self) -> Image.Image:
        raw = await self._run_adb(["exec-out", "screencap", "-p"])
        try:
            img = Image.open(io.BytesIO(raw)).convert("RGB")
            return img
        except Exception as e:
            raise RuntimeError(f"decode screenshot failed: {e}")

    async def _locate_element_with_vlm(self, element_name: str, image: Image.Image) -> TapTarget:
        buff = io.BytesIO()
        image.save(buff, format="PNG")
        b64 = base64.b64encode(buff.getvalue()).decode("utf-8")

        prompt = (
            "你是移动端 UI Grounding 模型。"
            "请在截图中找到目标元素并仅输出 JSON："
            "{\"x\":int,\"y\":int,\"confidence\":float,\"reason\":str}。"
            f"目标元素：{element_name}。"
        )

        payload = {
            "model": self.vlm_model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                    ],
                }
            ],
        }

        async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
            r = await client.post(f"{self.vlm_base_url}/v1/chat/completions", json=payload)
            r.raise_for_status()
            data = r.json()

        content = data["choices"][0]["message"]["content"]
        obj = json.loads(content)
        x = int(obj.get("x", -1))
        y = int(obj.get("y", -1))
        conf = float(obj.get("confidence", 0.0))
        if x < 0 or y < 0:
            raise RuntimeError(f"vlm locate invalid: {content}")

        return TapTarget(element_name=element_name, x=x, y=y, confidence=conf)

    async def _inject_tap(self, x: int, y: int) -> bool:
        # 先走一段曲线滑动，再落点轻触，模拟稳定的人类手势（用于测试鲁棒性）
        start = (x + random.randint(-60, 60), y + random.randint(-60, 60))
        points = generate_bezier_curve(start, (x, y), steps=8)

        for i in range(len(points) - 1):
            (x1, y1), (x2, y2) = points[i], points[i + 1]
            dur = random.randint(18, 35)
            await self._run_adb([
                "shell",
                "input",
                "swipe",
                str(x1),
                str(y1),
                str(x2),
                str(y2),
                str(dur),
            ])
            await asyncio.sleep(random.uniform(0.006, 0.018))

        # 最终 tap 前加轻微 jitter
        await asyncio.sleep(random.uniform(0.008, 0.028))
        await self._run_adb(["shell", "input", "tap", str(x), str(y)])
        return True

    async def tap_element(self, element_name: str) -> bool:
        img = await self.capture_screen()
        target = await self._locate_element_with_vlm(element_name, img)
        if target.confidence < 0.2:
            logger.warning("low confidence target: %s", target)
        return await self._inject_tap(target.x, target.y)

    async def type_text(self, text: str) -> bool:
        # 先点击输入框（视觉定位）
        await self.tap_element("输入框")
        await asyncio.sleep(random.uniform(0.05, 0.12))

        # Android input 对空格与特殊字符处理较弱，做最小转义
        safe = text.replace(" ", "%s")

        # 分片输入 + ms 级随机 jitter
        chunks = [safe[i : i + 8] for i in range(0, len(safe), 8)]
        for chunk in chunks:
            await self._run_adb(["shell", "input", "text", chunk])
            await asyncio.sleep(random.uniform(0.012, 0.055))

        return True


_driver: Optional[BaseDeviceDriver] = None


def get_driver() -> BaseDeviceDriver:
    global _driver
    if _driver is None:
        _driver = VLM_Android_Driver()
    return _driver


async def analyze_screen() -> dict:
    """兼容历史接口：返回截图基础信息。"""
    drv = get_driver()
    img = await drv.capture_screen()
    return {"width": img.width, "height": img.height}


async def click_at(x: int, y: int) -> bool:
    """兼容历史接口：直接坐标点击。"""
    drv = get_driver()
    if isinstance(drv, VLM_Android_Driver):
        return await drv._inject_tap(x, y)
    return False
