from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

_ROOT_LLM_PATH = Path(__file__).resolve().parent.parent / "llm_client.py"
_spec = importlib.util.spec_from_file_location("project_root_llm_client", _ROOT_LLM_PATH)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"Unable to load root llm_client from {_ROOT_LLM_PATH}")
_module = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _module
_spec.loader.exec_module(_module)
LLMClient = _module.LLMClient


def get_llm_client() -> LLMClient:
    return LLMClient(
        api_key=os.getenv('DEEPSEEK_API_KEY', ''),
        api_url=os.getenv('DEEPSEEK_API_URL', 'https://api.deepseek.com/chat/completions'),
        model=os.getenv('DEEPSEEK_MODEL', 'deepseek-chat'),
        temperature=float(os.getenv('DEEPSEEK_TEMPERATURE', '0.2')),
        max_tokens=int(os.getenv('DEEPSEEK_MAX_TOKENS', '256')),
        timeout=int(os.getenv('DEEPSEEK_TIMEOUT', '20')),
        max_retries=int(os.getenv('DEEPSEEK_MAX_RETRIES', '2')),
    )
