"""
Project Claw v14.3 - 工业级配置管理

规范：
- 所有敏感字段通过环境变量注入，绝不硬编码
- 字段校验在启动时完成，避免运行时错误
- 废弃的 lobster/feishu/openclaw 字段已清除
"""
from __future__ import annotations

import re
from typing import List, Optional

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
    _USE_PYDANTIC_V2 = True
except ImportError:
    from pydantic import BaseSettings  # type: ignore
    _USE_PYDANTIC_V2 = False

from pydantic import field_validator, model_validator


class Settings(BaseSettings):
    # ═══ DeepSeek LLM ══════════════════════════════════════════
    DEEPSEEK_API_KEY:     str   = ""
    DEEPSEEK_API_URL:     str   = "https://api.deepseek.com/chat/completions"
    DEEPSEEK_MODEL:       str   = "deepseek-chat"
    DEEPSEEK_TIMEOUT:     int   = 15
    DEEPSEEK_MAX_TOKENS:  int   = 200
    DEEPSEEK_TEMPERATURE: float = 0.7
    DEEPSEEK_MAX_RETRIES: int   = 3

    # ═══ 支付 ══════════════════════════════════════════════════
    PAYMENT_QR_PATH: str = "./payment_qr.png"

    # ═══ 系统提示词 ════════════════════════════════════════════
    SYSTEM_PROMPT: str = "你是一个热情的店老板，回话简短接地气，叫人'兄弟'。"

    # ═══ OCR ═══════════════════════════════════════════════════
    OCR_LANGUAGES:       List[str] = ["ch_sim", "en"]
    OCR_FAIL_MAX_RETRIES: int      = 3

    # ═══ 本地记忆（B端菜单底价）══════════════════════════════
    LOCAL_MEMORY_ENABLED:    bool = True
    LOCAL_MEMORY_DB_DIR:     str  = "./claw_db"
    LOCAL_MEMORY_CSV:        str  = "menu.csv"
    LOCAL_MEMORY_TOP_K:      int  = 3
    LOCAL_MEMORY_EMBED_MODEL: str = "all-MiniLM-L6-v2"

    # ═══ A2A 协议 ══════════════════════════════════════════════
    A2A_MERCHANT_ID:    str   = "box-001"
    A2A_MERCHANT_TAGS:  str   = ""
    A2A_SIGNALING_URL:  str   = ""
    A2A_SIGNING_SECRET: str   = "claw-a2a-signing-secret"
    A2A_ENCRYPTION_KEY: str   = ""

    # ═══ 内部接口鉴权 ══════════════════════════════════════════
    INTERNAL_API_TOKEN: str = ""

    # ═══ Redis ═════════════════════════════════════════════════
    REDIS_URL:                          str   = ""
    IDEMPOTENCY_TTL_SECONDS:            int   = 300
    EXECUTE_TRADE_SEND_TIMEOUT_SECONDS: float = 4.0
    PROFILE_TTL_SECONDS:                int   = 86400

    # ═══ 云端信令服务器 ════════════════════════════════════════
    SIGNALING_HOST:       str = "127.0.0.1"
    SIGNALING_PORT:       int = 8765
    SIGNALING_HTTP_SCHEME: str = "http"
    SIGNALING_WS_SCHEME:  str  = "ws"

    # ═══ 日志 ══════════════════════════════════════════════════
    LOG_LEVEL:           str = "INFO"
    LOG_FILE:            str = "claw.log"
    LOG_FORMAT:          str = "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
    LOG_DIR:             str = "logs"
    SHOWCASE_EVENT_FILE: str = "logs/showcase_events.jsonl"

    # ═══ 谈判引擎 ══════════════════════════════════════════════
    MATCH_ROUNDS:     int   = 5
    MATCH_THRESHOLD:  float = 90.0

    if _USE_PYDANTIC_V2:
        model_config = SettingsConfigDict(
            env_file=".env",
            case_sensitive=True,
            extra="ignore",
        )
    else:
        class Config:
            env_file = ".env"
            case_sensitive = True
            extra = "ignore"

    # ─── 字段校验 ─────────────────────────────────────────────
    @field_validator("DEEPSEEK_TEMPERATURE")
    @classmethod
    def _check_temperature(cls, v: float) -> float:
        if not 0.0 <= v <= 2.0:
            raise ValueError(f"DEEPSEEK_TEMPERATURE 必须在 0~2 之间，当前: {v}")
        return v

    @field_validator("SIGNALING_HTTP_SCHEME")
    @classmethod
    def _check_http_scheme(cls, v: str) -> str:
        if v not in ("http", "https"):
            raise ValueError(f"SIGNALING_HTTP_SCHEME 必须是 http 或 https，当前: {v}")
        return v

    @field_validator("SIGNALING_WS_SCHEME")
    @classmethod
    def _check_ws_scheme(cls, v: str) -> str:
        if v not in ("ws", "wss"):
            raise ValueError(f"SIGNALING_WS_SCHEME 必须是 ws 或 wss，当前: {v}")
        return v

    @field_validator("LOG_LEVEL")
    @classmethod
    def _check_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid:
            raise ValueError(f"LOG_LEVEL 必须是 {valid}，当前: {v}")
        return v.upper()

    # ─── 属性（URL 组装）────────────────────────────────────────
    @property
    def signaling_http_base_url(self) -> str:
        if self.A2A_SIGNALING_URL:
            m = re.match(r"(wss?://[^/]+)", self.A2A_SIGNALING_URL)
            if m:
                return m.group(1).replace("wss://", "https://").replace("ws://", "http://")
        return f"{self.SIGNALING_HTTP_SCHEME}://{self.SIGNALING_HOST}:{self.SIGNALING_PORT}"

    @property
    def signaling_ws_base_url(self) -> str:
        if self.A2A_SIGNALING_URL:
            m = re.match(r"(wss?://[^/]+)", self.A2A_SIGNALING_URL)
            if m:
                return m.group(1)
        return f"{self.SIGNALING_WS_SCHEME}://{self.SIGNALING_HOST}:{self.SIGNALING_PORT}"

    def signaling_merchant_ws_url(self, merchant_id: str) -> str:
        return f"{self.signaling_ws_base_url}/ws/a2a/merchant/{merchant_id}"


settings = Settings()
