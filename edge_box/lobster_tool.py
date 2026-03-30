"""
LangChain Tool - PhysicalActionTool
将微信物理操作封装为 LangChain 标准 Tool Class。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional, Type

import cv2
import numpy as np
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from edge_box.physical_tool import PhysicalTool

logger = logging.getLogger("claw.edge.lobster_tool")


class SendWechatReplyInput(BaseModel):
    text: str = Field(..., description="要发送到微信的回复文本")


class PhysicalActionTool(BaseTool):
    """LangChain 标准物理执行工具。"""

    name: str = "physical_action_tool"
    description: str = "发送微信回复，并对发送后UI状态做视觉验证。"
    args_schema: Type[BaseModel] = SendWechatReplyInput

    physical: PhysicalTool
    input_x: float = 540.0
    input_y: float = 1800.0
    max_retries: int = 3

    model_config = {"arbitrary_types_allowed": True}

    async def get_latest_chat(self) -> Optional[str]:
        """异步读取最新顾客消息。"""
        return await asyncio.to_thread(self.physical.detect_new_customer_message)

    async def send_wechat_reply(self, text: str) -> bool:
        """异步发送消息，失败自动重试（最多3次）。"""
        text = (text or "").strip()
        if not text:
            return False

        for attempt in range(1, self.max_retries + 1):
            ok = await asyncio.to_thread(self._send_once_and_verify, text)
            if ok:
                logger.info(f"[PhysicalActionTool] send ok attempt={attempt}")
                return True
            logger.warning(f"[PhysicalActionTool] send verify failed attempt={attempt}")
            await asyncio.sleep(0.25 * attempt)

        return False

    async def show_fee_reminder(self, text: str = "欠费提醒：余额不足，已停止接单") -> bool:
        reminder = (text or "欠费提醒：余额不足，已停止接单").strip()
        if not reminder.startswith("欠费提醒"):
            reminder = f"欠费提醒：{reminder}"
        return await self.send_wechat_reply(reminder)

    def verify_ui_state(self, before_img: np.ndarray, after_img: np.ndarray) -> bool:
        """
        视觉验证发送成功：
        1) 聊天区域发生变化（新消息气泡出现）
        2) 输入框区域文本密度下降（输入框被清空）
        """
        if before_img is None or after_img is None:
            return False
        if before_img.shape != after_img.shape:
            return False

        h, w = before_img.shape[:2]

        # 聊天区域（中上部）变化检测
        chat_before = before_img[int(h * 0.18) : int(h * 0.86), int(w * 0.05) : int(w * 0.95)]
        chat_after = after_img[int(h * 0.18) : int(h * 0.86), int(w * 0.05) : int(w * 0.95)]
        chat_diff = cv2.absdiff(chat_before, chat_after)
        chat_changed = float(chat_diff.mean()) >= 1.5

        # 输入框区域（底部）文本密度变化
        x0 = max(0, int(self.input_x - w * 0.35))
        x1 = min(w, int(self.input_x + w * 0.35))
        y0 = max(0, int(self.input_y - h * 0.045))
        y1 = min(h, int(self.input_y + h * 0.045))

        before_input = before_img[y0:y1, x0:x1]
        after_input = after_img[y0:y1, x0:x1]
        if before_input.size == 0 or after_input.size == 0:
            return False

        before_gray = cv2.cvtColor(before_input, cv2.COLOR_BGR2GRAY)
        after_gray = cv2.cvtColor(after_input, cv2.COLOR_BGR2GRAY)

        # 深色像素占比近似文本密度
        before_text_ratio = float((before_gray < 120).mean())
        after_text_ratio = float((after_gray < 120).mean())
        input_cleared = after_text_ratio <= before_text_ratio * 0.75 or after_text_ratio < 0.015

        return bool(chat_changed and input_cleared)

    def _capture_screen(self) -> Optional[np.ndarray]:
        if not self.physical or not self.physical._d:
            return None
        return self.physical._take_screenshot()

    def _send_once_and_verify(self, text: str) -> bool:
        before = self._capture_screen()
        sent_ok = self.physical.send_message(self.input_x, self.input_y, text)
        if not sent_ok:
            return False

        # UI稳定时间
        import time

        time.sleep(0.35)
        after = self._capture_screen()
        return self.verify_ui_state(before, after)

    def _run(self, text: str, run_manager: Any = None) -> str:
        """同步调用兜底：优先给非异步链路兼容。"""
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                raise RuntimeError("Use async invoke for PhysicalActionTool inside running event loop")
        except RuntimeError:
            pass

        ok = asyncio.run(self.send_wechat_reply(text))
        return "ok" if ok else "failed"

    async def _arun(self, text: str, run_manager: Any = None) -> str:
        ok = await self.send_wechat_reply(text)
        return "ok" if ok else "failed"
