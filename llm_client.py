"""
Project Claw - 统一 LLM 客户端
支持 DeepSeek，预留 OpenAI/Claude 扩展接口
"""
import requests
import json
import logging
import time
from typing import Optional, List, Dict
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class LLMMessage:
    role: str  # system / user / assistant
    content: str


class LLMClient:
    """
    统一 LLM 客户端
    工厂模式，后期可扩展 OpenAI / Claude / 本地模型
    """

    def __init__(
        self,
        api_key: str,
        api_url: str = "https://api.deepseek.com/chat/completions",
        model: str = "deepseek-chat",
        temperature: float = 0.7,
        max_tokens: int = 200,
        timeout: int = 15,
        max_retries: int = 3,
    ):
        self.api_key = api_key
        self.api_url = api_url
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.max_retries = max_retries

    def chat(self, messages: List[LLMMessage], temperature: float = None) -> Optional[str]:
        """多轮对话接口"""
        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": self.max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        for attempt in range(self.max_retries):
            try:
                resp = requests.post(
                    self.api_url,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"].strip()
            except requests.exceptions.Timeout:
                logger.warning(f"LLM 超时 (attempt {attempt+1}/{self.max_retries})")
                time.sleep(1)
            except Exception as e:
                logger.error(f"LLM 请求失败 (attempt {attempt+1}): {e}")
                time.sleep(1)
        return None

    def ask(self, prompt: str, system: str = None) -> Optional[str]:
        """单轮问答接口（兼容旧版）"""
        messages = []
        if system:
            messages.append(LLMMessage(role="system", content=system))
        messages.append(LLMMessage(role="user", content=prompt))
        return self.chat(messages)

    def ask_json(self, prompt: str, system: str = None) -> Optional[dict]:
        """返回 JSON 的问答接口，自动解析"""
        result = self.ask(prompt, system)
        if not result:
            return None
        try:
            # 尝试提取 JSON 块
            if "```json" in result:
                result = result.split("```json")[1].split("```")[0].strip()
            elif "```" in result:
                result = result.split("```")[1].split("```")[0].strip()
            return json.loads(result)
        except Exception as e:
            logger.error(f"JSON 解析失败: {e} | 原始内容: {result[:200]}")
            return None

    def ask_messages(self, messages: List[dict], temperature: float = None) -> Optional[str]:
        """
        直接接受 OpenAI 格式的 messages 列表
        [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
        用于多轮对话上下文传入。
        """
        payload = {
            "model":       self.model,
            "messages":    messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens":  self.max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type":  "application/json",
        }
        for attempt in range(self.max_retries):
            try:
                resp = requests.post(
                    self.api_url,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"].strip()
            except requests.exceptions.Timeout:
                logger.warning(f"LLM 超时 (attempt {attempt+1}/{self.max_retries})")
                time.sleep(1)
            except Exception as e:
                logger.error(f"LLM 请求失败 (attempt {attempt+1}): {e}")
                time.sleep(1)
        return None

    def ask_with_history(self, user_msg: str, history: List[dict], system: str = None) -> Optional[str]:
        """
        带历史上下文的问答。history 格式同 ask_messages。
        """
        msgs: List[dict] = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(history)
        msgs.append({"role": "user", "content": user_msg})
        return self.ask_messages(msgs)
