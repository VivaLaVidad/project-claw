from __future__ import annotations

import base64
import json
import os
import re
import subprocess
from dataclasses import dataclass
from typing import Any, Optional

import requests


@dataclass
class VLMObserverConfig:
    endpoint: str = os.getenv("VLM_ENDPOINT", "http://localhost:11434/v1/chat/completions")
    model: str = os.getenv("VLM_MODEL", "qwen2.5-vl")
    timeout_sec: int = int(os.getenv("VLM_TIMEOUT_SEC", "30"))
    device_serial: Optional[str] = os.getenv("DEVICE_SERIAL")


class VLMObserver:
    def __init__(self, config: Optional[VLMObserverConfig] = None):
        self.config = config or VLMObserverConfig()

    def capture_screen_base64(self) -> str:
        cmd = ["adb"]
        if self.config.device_serial:
            cmd += ["-s", self.config.device_serial]
        cmd += ["exec-out", "screencap", "-p"]

        raw = subprocess.check_output(cmd, timeout=10)
        return base64.b64encode(raw).decode("utf-8")

    def plan_actions(self, instruction: str) -> dict[str, Any]:
        screenshot_b64 = self.capture_screen_base64()
        prompt = (
            "你是 Android 视觉动作规划器。根据截图和指令输出 JSON。"
            "只允许动作类型 CLICK/SWIPE/TYPE/WAIT。"
            "格式: {\"actions\":[{\"type\":\"CLICK\",\"params\":{...}}],\"goal\":\"...\"}。"
            f"指令: {instruction}"
        )
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": "只输出 JSON，不要解释。"},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"}},
                    ],
                },
            ],
            "temperature": 0,
            "max_tokens": 600,
        }
        resp = requests.post(self.config.endpoint, json=payload, timeout=self.config.timeout_sec)
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"]
        return self._parse_json(text)

    def validate_state_change(self, before_b64: str, after_b64: str, goal: str) -> dict[str, Any]:
        prompt = (
            "比较两张 Android 截图（before/after），判断执行动作后状态是否发生了预期变化。"
            "只输出 JSON: {\"changed\":true/false,\"confidence\":0~1,\"reason\":\"...\"}。"
            f"目标: {goal}"
        )
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": "只输出 JSON，不要解释。"},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{before_b64}"}},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{after_b64}"}},
                    ],
                },
            ],
            "temperature": 0,
            "max_tokens": 300,
        }
        try:
            resp = requests.post(self.config.endpoint, json=payload, timeout=self.config.timeout_sec)
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"]
            result = self._parse_json(text)
            if "changed" in result:
                return result
        except Exception:
            pass

        # fallback：基础位级比较
        changed = before_b64 != after_b64
        return {"changed": changed, "confidence": 0.4, "reason": "fallback-bytes-compare"}

    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any]:
        txt = (raw or "").strip()
        if txt.startswith("```"):
            m = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", txt)
            if m:
                txt = m.group(1)
        if not txt.startswith("{"):
            m = re.search(r"\{[\s\S]*\}", txt)
            if m:
                txt = m.group(0)
        return json.loads(txt)
