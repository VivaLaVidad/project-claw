"""
OpenMAIC Adapter
Industrial integration path:
- Health check via /api/health
- Chat generation via /api/chat (SSE stream)
"""
import json
import time
from typing import Dict, List, Optional

import requests

from settings import load_settings


class OpenMAICAdapter:
    def __init__(self):
        self.settings = load_settings()
        self.base_url = self.settings.openmaic_base_url.rstrip("/")
        self.timeout = self.settings.openmaic_timeout_seconds
        self.agent_ids = [x.strip() for x in self.settings.openmaic_agent_ids.split(",") if x.strip()]
        if not self.agent_ids:
            self.agent_ids = ["default-1"]

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.settings.openmaic_access_code:
            headers["Authorization"] = f"Bearer {self.settings.openmaic_access_code}"
        return headers

    def health_check(self) -> Dict:
        url = f"{self.base_url}/api/health"
        resp = requests.get(url, headers=self._headers(), timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def generate_reply(
        self,
        user_message: str,
        inventory_info: Dict,
        short_memory: str,
        long_profile: Dict,
        fallback_api_key: str,
    ) -> str:
        """
        Call OpenMAIC /api/chat and extract the final assistant text from SSE deltas.
        """
        prompt = (
            "你是餐馆老板对话代理。"
            "请基于库存、记忆、画像给出简短可执行回复（<=15字，热情）。\n"
            f"顾客消息: {user_message}\n"
            f"库存信息: {inventory_info}\n"
            f"短期记忆: {short_memory}\n"
            f"长期画像: {long_profile}"
        )

        now = int(time.time() * 1000)
        payload = {
            "messages": [
                {
                    "id": f"user-{now}",
                    "role": "user",
                    "parts": [{"type": "text", "text": prompt}],
                    "metadata": {"createdAt": now},
                }
            ],
            "storeState": {
                "stage": None,
                "scenes": [],
                "currentSceneId": None,
                "mode": "autonomous",
                "whiteboardOpen": False,
            },
            "config": {
                "agentIds": self.agent_ids,
                "sessionType": "qa",
            },
            # OpenMAIC chat route requires apiKey (or server-side provider config)
            "apiKey": fallback_api_key,
            "model": self.settings.openmaic_model,
        }

        url = f"{self.base_url}/api/chat"
        response = requests.post(
            url,
            headers=self._headers(),
            json=payload,
            timeout=self.timeout,
            stream=True,
        )
        response.raise_for_status()

        chunks: List[str] = []
        for raw_line in response.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            line = raw_line.strip()
            if not line.startswith("data: "):
                continue
            if line == "data: [DONE]":
                break

            try:
                event = json.loads(line[6:])
            except json.JSONDecodeError:
                continue

            event_type = event.get("type")
            data = event.get("data", {})

            if event_type == "text_delta":
                delta = data.get("content", "")
                if delta:
                    chunks.append(delta)
            elif event_type == "error":
                message = data.get("message", "openmaic unknown error")
                raise RuntimeError(message)

        text = "".join(chunks).strip()
        if not text:
            raise RuntimeError("OpenMAIC returned empty text")
        return text
