from __future__ import annotations

import asyncio
import re
from typing import Any

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_fixed

from config import settings
from llm_client import LLMClient
from logger_setup import setup_logger


logger = setup_logger("claw.siri")

app = FastAPI(title="Project Claw Siri Webhook", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SiriIntentRequest(BaseModel):
    spoken_text: str = Field(..., min_length=2)
    client_id: str = Field(..., min_length=1)


class ParsedTradeRequest(BaseModel):
    item: str = Field(..., min_length=1)
    max_price: float = Field(..., gt=0)


class TradeCoordinator:
    """极简协调器：把 Siri 意图推入现有 A2A 信令广播池。"""

    def __init__(self, signaling_base_url: str | None = None):
        self.signaling_base_url = (signaling_base_url or settings.signaling_http_base_url).rstrip("/")

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(0.5))
    def push_trade_request(self, client_id: str, trade: ParsedTradeRequest) -> dict[str, Any]:
        resp = requests.post(
            f"{self.signaling_base_url}/intent",
            json={
                "client_id": client_id,
                "location": "SiriShortcut",
                "demand_text": f"想吃{trade.item}",
                "max_price": trade.max_price,
                "timeout": 2.0,
            },
            timeout=4,
        )
        resp.raise_for_status()
        return resp.json()


class SiriIntentParser:
    def __init__(self):
        api_key = settings.DEEPSEEK_API_KEY.strip()
        self.llm = LLMClient(
            api_key=api_key,
            model=settings.DEEPSEEK_MODEL,
            temperature=0.1,
            max_tokens=80,
            timeout=6,
            max_retries=2,
        ) if api_key else None

    def parse(self, spoken_text: str) -> ParsedTradeRequest:
        parsed = self._parse_with_llm(spoken_text)
        if parsed:
            return parsed
        fallback = self._parse_with_regex(spoken_text)
        if fallback:
            return fallback
        raise ValueError("unable_to_parse_trade_request")

    def _parse_with_llm(self, spoken_text: str) -> ParsedTradeRequest | None:
        if not self.llm:
            return None
        system = (
            "你是一个点餐语音解析器。"
            "请把用户自然语言严格解析为 JSON，格式为: "
            '{"item":"菜品名","max_price":15}。'
            "不要输出任何解释。"
        )
        prompt = f"用户语音：{spoken_text}"
        result = self.llm.ask_json(prompt=prompt, system=system)
        if not result:
            return None
        try:
            return ParsedTradeRequest(item=str(result["item"]).strip(), max_price=float(result["max_price"]))
        except Exception:
            return None

    def _parse_with_regex(self, spoken_text: str) -> ParsedTradeRequest | None:
        text = spoken_text.replace("，", ",").replace("块钱", "块")
        price_match = re.search(r"(\d+(?:\.\d+)?)\s*(块|元)", text)
        item_match = re.search(r"(?:要|想|吃|来一份|帮我点)?([\u4e00-\u9fa5A-Za-z0-9]{2,12})(?:,|\d|块|元|以内|以下)", text)
        if not item_match:
            item_match = re.search(r"([\u4e00-\u9fa5A-Za-z0-9]{2,12})", text)
        if not item_match or not price_match:
            return None
        return ParsedTradeRequest(item=item_match.group(1), max_price=float(price_match.group(1)))


trade_coordinator = TradeCoordinator()
intent_parser = SiriIntentParser()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/siri_intent")
async def siri_intent(body: SiriIntentRequest) -> dict[str, str]:
    try:
        logger.vision_scan(body.spoken_text)
        trade = await asyncio.to_thread(intent_parser.parse, body.spoken_text)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"解析失败: {e}") from e

    logger.a2a_handshake(f"siri:{body.client_id}:{trade.item}:{trade.max_price}")

    async def _dispatch() -> None:
        try:
            await asyncio.to_thread(trade_coordinator.push_trade_request, body.client_id, trade)
        except Exception:
            return

    asyncio.create_task(_dispatch())
    speech_reply = f"已为您锁定一家{trade.item}，{int(trade.max_price)}元，老板正在接单"
    return {"speech_reply": speech_reply}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("cloud_server.api_server_pro:app", host=settings.SIRI_HOST, port=settings.SIRI_PORT, log_level="info")
