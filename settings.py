"""
Project Claw runtime settings.
Load all secrets/config from environment variables.
"""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    deepseek_api_key: str
    deepseek_base_url: str
    feishu_app_id: str
    feishu_app_secret: str
    feishu_app_token: str
    feishu_table_id: str
    openmaic_enabled: bool
    openmaic_base_url: str
    openmaic_access_code: str
    openmaic_model: str
    openmaic_agent_ids: str
    openmaic_timeout_seconds: int


def _as_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_settings() -> Settings:
    return Settings(
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        feishu_app_id=os.getenv("FEISHU_APP_ID", ""),
        feishu_app_secret=os.getenv("FEISHU_APP_SECRET", ""),
        feishu_app_token=os.getenv("FEISHU_APP_TOKEN", ""),
        feishu_table_id=os.getenv("FEISHU_TABLE_ID", ""),
        openmaic_enabled=_as_bool(os.getenv("OPENMAIC_ENABLED"), default=True),
        openmaic_base_url=os.getenv("OPENMAIC_BASE_URL", "http://localhost:3000"),
        openmaic_access_code=os.getenv("OPENMAIC_ACCESS_CODE", ""),
        openmaic_model=os.getenv("OPENMAIC_MODEL", "deepseek:deepseek-chat"),
        openmaic_agent_ids=os.getenv("OPENMAIC_AGENT_IDS", "default-1"),
        openmaic_timeout_seconds=int(os.getenv("OPENMAIC_TIMEOUT_SECONDS", "30")),
    )
