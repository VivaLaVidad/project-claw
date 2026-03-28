"""
llm_client.py - Project Claw v14.3
统一 LLM 客户端（工业级重构）

改进：
- 消除 chat/ask_messages 重复 HTTP 代码，统一走 _call()
- tenacity 重试：指数退避，只在网络/5xx 时重试
- 流式输出支持（stream=True）
- 完整 token 用量追踪
- 支持 DeepSeek / OpenAI / 任意兼容接口（工厂方法）
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Generator, Iterator, List, Optional

import requests
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger("claw.llm")


# ─── 数据类 ──────────────────────────────────────────────────
@dataclass
class LLMMessage:
    role:    str   # system / user / assistant
    content: str

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


@dataclass
class LLMUsage:
    prompt_tokens:     int = 0
    completion_tokens: int = 0
    total_tokens:      int = 0


@dataclass
class LLMResponse:
    content: str
    usage:   LLMUsage = field(default_factory=LLMUsage)
    model:   str      = ""
    latency: float    = 0.0


# ─── 可重试的异常类型 ──────────────────────────────────────────
class _RetryableError(Exception):
    """网络超时或 5xx 错误，触发 tenacity 重试。"""


# ─── LLMClient ────────────────────────────────────────────────
class LLMClient:
    """
    统一 LLM 客户端。
    工厂模式，支持 DeepSeek / OpenAI / 任意兼容接口。

    用法：
        client = LLMClient.deepseek(api_key="sk-...")
        resp   = client.chat([LLMMessage("user", "你好")])
        print(resp.content)
    """

    def __init__(
        self,
        api_key:     str,
        api_url:     str   = "https://api.deepseek.com/chat/completions",
        model:       str   = "deepseek-chat",
        temperature: float = 0.7,
        max_tokens:  int   = 200,
        timeout:     int   = 15,
        max_retries: int   = 3,
    ) -> None:
        if not api_key:
            logger.warning("[LLMClient] api_key 为空，LLM 调用将失败")
        self.api_key     = api_key
        self.api_url     = api_url
        self.model       = model
        self.temperature = temperature
        self.max_tokens  = max_tokens
        self.timeout     = timeout
        self.max_retries = max_retries
        self._session    = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type":  "application/json",
        })
        # 累计用量统计
        self.total_usage = LLMUsage()

    # ── 工厂方法 ───────────────────────────────────────────────
    @classmethod
    def deepseek(
        cls,
        api_key:     str,
        model:       str   = "deepseek-chat",
        temperature: float = 0.7,
        max_tokens:  int   = 200,
    ) -> "LLMClient":
        return cls(
            api_key=api_key,
            api_url="https://api.deepseek.com/chat/completions",
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    @classmethod
    def openai(
        cls,
        api_key:     str,
        model:       str   = "gpt-4o-mini",
        temperature: float = 0.7,
        max_tokens:  int   = 200,
    ) -> "LLMClient":
        return cls(
            api_key=api_key,
            api_url="https://api.openai.com/v1/chat/completions",
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    # ── 核心：统一 HTTP 调用 ────────────────────────────────────
    def _call(
        self,
        messages:    List[dict],
        temperature: Optional[float] = None,
        stream:      bool = False,
    ) -> requests.Response:
        """
        底层 HTTP 调用，由 tenacity 包裹重试。
        只有 _RetryableError 才触发重试。
        """
        payload = {
            "model":       self.model,
            "messages":    messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens":  self.max_tokens,
            "stream":      stream,
        }

        @retry(
            retry=retry_if_exception_type(_RetryableError),
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
            reraise=False,
        )
        def _do() -> requests.Response:
            try:
                resp = self._session.post(
                    self.api_url,
                    json=payload,
                    timeout=self.timeout,
                    stream=stream,
                )
                if resp.status_code >= 500:
                    raise _RetryableError(f"5xx: {resp.status_code}")
                if resp.status_code == 429:
                    time.sleep(2)
                    raise _RetryableError("rate limited")
                resp.raise_for_status()
                return resp
            except requests.exceptions.Timeout:
                raise _RetryableError("timeout")
            except requests.exceptions.ConnectionError:
                raise _RetryableError("connection error")

        return _do()

    def _to_dicts(self, messages: List[LLMMessage]) -> List[dict]:
        return [m.to_dict() for m in messages]

    # ── 公开接口 ───────────────────────────────────────────────
    def chat(
        self,
        messages:    List[LLMMessage],
        temperature: Optional[float] = None,
    ) -> Optional[LLMResponse]:
        """多轮对话，返回 LLMResponse（含 token 用量）。"""
        t0 = time.time()
        try:
            resp = self._call(self._to_dicts(messages), temperature)
            data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()
            usage   = data.get("usage", {})
            llm_usage = LLMUsage(
                prompt_tokens     = usage.get("prompt_tokens", 0),
                completion_tokens = usage.get("completion_tokens", 0),
                total_tokens      = usage.get("total_tokens", 0),
            )
            self.total_usage.prompt_tokens     += llm_usage.prompt_tokens
            self.total_usage.completion_tokens += llm_usage.completion_tokens
            self.total_usage.total_tokens      += llm_usage.total_tokens
            return LLMResponse(
                content = content,
                usage   = llm_usage,
                model   = data.get("model", self.model),
                latency = round(time.time() - t0, 3),
            )
        except Exception as e:
            logger.error(f"[LLMClient] chat failed: {e}")
            return None

    def ask(
        self,
        prompt:      str,
        system:      Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> Optional[str]:
        """单轮问答，返回字符串（兼容旧接口）。"""
        messages = []
        if system:
            messages.append(LLMMessage("system", system))
        messages.append(LLMMessage("user", prompt))
        resp = self.chat(messages, temperature)
        return resp.content if resp else None

    def ask_json(
        self,
        prompt:      str,
        system:      Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> Optional[dict]:
        """返回解析后的 JSON dict，自动提取代码块。"""
        raw = self.ask(prompt, system, temperature)
        if not raw:
            return None
        text = raw
        for marker in ["```json", "```"]:
            if marker in text:
                parts = text.split(marker)
                if len(parts) >= 2:
                    text = parts[1].split("```")[0].strip()
                    break
        try:
            return json.loads(text)
        except Exception as e:
            logger.error(f"[LLMClient] JSON parse failed: {e} | raw={raw[:200]}")
            return None

    def ask_messages(
        self,
        messages:    List[dict],
        temperature: Optional[float] = None,
    ) -> Optional[str]:
        """直接接受 OpenAI 格式 messages 列表（兼容旧接口）。"""
        t0 = time.time()
        try:
            resp = self._call(messages, temperature)
            return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.error(f"[LLMClient] ask_messages failed: {e}")
            return None

    def stream(
        self,
        prompt:      str,
        system:      Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> Iterator[str]:
        """
        流式输出接口（SSE）。
        逐 token yield 字符串，适合实时显示。
        """
        messages = []
        if system:
            messages.append({"role": "system",  "content": system})
        messages.append({"role": "user", "content": prompt})
        try:
            resp = self._call(messages, temperature, stream=True)
            for line in resp.iter_lines():
                if not line:
                    continue
                text = line.decode("utf-8") if isinstance(line, bytes) else line
                if text.startswith("data: "):
                    text = text[6:]
                if text == "[DONE]":
                    return
                try:
                    delta = json.loads(text)["choices"][0]["delta"].get("content", "")
                    if delta:
                        yield delta
                except Exception:
                    continue
        except Exception as e:
            logger.error(f"[LLMClient] stream failed: {e}")
            return

    def usage_summary(self) -> dict:
        """返回累计 token 用量统计。"""
        return {
            "prompt_tokens":     self.total_usage.prompt_tokens,
            "completion_tokens": self.total_usage.completion_tokens,
            "total_tokens":      self.total_usage.total_tokens,
        }
