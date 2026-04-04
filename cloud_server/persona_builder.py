from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List

from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy import select
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from cloud_server.data_models import ClientORM, MerchantORM
from cloud_server.db import session_scope


class LLMOutputError(RuntimeError):
    pass


class ClientPersonaLLMOutput(BaseModel):
    price_sensitivity: float = Field(..., ge=0.0, le=1.0)
    negotiation_style: str = Field(..., min_length=1, max_length=64)
    taste_preference: str = Field(..., min_length=1, max_length=64)

    @field_validator('negotiation_style', 'taste_preference')
    @classmethod
    def _strip_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError('empty_text_not_allowed')
        return text


class MerchantPersonaLLMOutput(BaseModel):
    bottom_line_rules: List[str] = Field(..., min_length=1)
    negotiation_style: str = Field(..., min_length=1, max_length=64)
    sales_tone: str = Field(..., min_length=1, max_length=64)

    @field_validator('bottom_line_rules')
    @classmethod
    def _validate_rules(cls, value: List[str]) -> List[str]:
        rules = [str(v).strip() for v in value if str(v).strip()]
        if not rules:
            raise ValueError('bottom_line_rules_required')
        return rules


class ClientPersonaRecord(BaseModel):
    client_id: str
    transcript: str
    price_sensitivity: float
    negotiation_style: str
    taste_preference: str
    buyer_system_prompt: str
    created_at: float


class MerchantPersonaRecord(BaseModel):
    merchant_id: str
    transcript: str
    menu_floor_data: Dict[str, float]
    bottom_line_rules: List[str]
    negotiation_style: str
    sales_tone: str
    sales_system_prompt: str
    created_at: float


@dataclass
class PersonaBuilderBase:
    llm_client: Any

    def _parse_json(self, raw: str) -> Dict[str, Any]:
        text = (raw or '').strip()
        if not text:
            raise LLMOutputError('empty_llm_output')
        if '```json' in text:
            text = text.split('```json', 1)[1].split('```', 1)[0].strip()
        elif '```' in text:
            text = text.split('```', 1)[1].split('```', 1)[0].strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMOutputError(f'invalid_json:{exc}') from exc

    async def _ask_json(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        if self.llm_client is None:
            raise LLMOutputError('llm_client_missing')
        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ]
        raw = None
        if hasattr(self.llm_client, 'ask_messages'):
            raw = await asyncio.to_thread(self.llm_client.ask_messages, messages, 0.1)
        elif hasattr(self.llm_client, 'ask'):
            prompt = f"SYSTEM:\n{system_prompt}\n\nUSER:\n{user_prompt}"
            raw = await asyncio.to_thread(self.llm_client.ask, prompt)
        if not raw:
            raise LLMOutputError('empty_llm_response')
        return self._parse_json(raw)


class ClientPersonaBuilder(PersonaBuilderBase):
    @retry(
        retry=retry_if_exception_type((LLMOutputError, ValidationError)),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def build_from_transcript(self, client_id: str, transcript: str) -> ClientPersonaRecord:
        transcript = str(transcript or '').strip()
        if not transcript:
            raise ValueError('transcript_required')

        system_prompt = (
            '你是 Project Claw 的数字孪生初始化引擎。'
            '必须严格输出 JSON，不允许 markdown，不允许解释。'
            'JSON schema={"price_sensitivity":number,"negotiation_style":string,"taste_preference":string}。'
            'price_sensitivity 必须在 0 到 1 之间。'
        )
        user_prompt = f'用户语音转本：{transcript}'
        parsed = ClientPersonaLLMOutput.model_validate(await self._ask_json(system_prompt, user_prompt))

        buyer_system_prompt = (
            f"你是该用户的 BuyerAgent。用户偏好：{parsed.taste_preference}；"
            f"谈判风格：{parsed.negotiation_style}；价格敏感度：{parsed.price_sensitivity:.2f}。"
            '你需要在保证成交可能性的前提下，优先争取更优价格，并根据口味偏好选择更匹配的餐品。'
        )

        record = ClientPersonaRecord(
            client_id=client_id,
            transcript=transcript,
            price_sensitivity=parsed.price_sensitivity,
            negotiation_style=parsed.negotiation_style,
            taste_preference=parsed.taste_preference,
            buyer_system_prompt=buyer_system_prompt,
            created_at=time.time(),
        )
        await self._save_client_record(record)
        return record

    async def _save_client_record(self, record: ClientPersonaRecord) -> None:
        async with session_scope() as session:
            row = await session.get(ClientORM, record.client_id)
            if row is None:
                row = ClientORM(client_id=record.client_id)
                session.add(row)
            row.persona_vector = {
                'transcript': record.transcript,
                'price_sensitivity': record.price_sensitivity,
                'negotiation_style': record.negotiation_style,
                'taste_preference': record.taste_preference,
                'created_at': record.created_at,
            }
            row.buyer_system_prompt = record.buyer_system_prompt
            row.taste_preference = record.taste_preference
            row.negotiation_style = record.negotiation_style
            row.updated_at = time.time()


class MerchantPersonaBuilder(PersonaBuilderBase):
    @retry(
        retry=retry_if_exception_type((LLMOutputError, ValidationError)),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def build_from_transcript(self, merchant_id: str, transcript: str, menu_floor_data: Dict[str, float]) -> MerchantPersonaRecord:
        transcript = str(transcript or '').strip()
        if not transcript:
            raise ValueError('transcript_required')
        if not menu_floor_data:
            raise ValueError('menu_floor_data_required')

        normalized_menu = {str(k): float(v) for k, v in menu_floor_data.items()}
        system_prompt = (
            '你是 Project Claw 的商家数字孪生初始化引擎。'
            '必须严格输出 JSON，不允许 markdown，不允许解释。'
            'JSON schema={"bottom_line_rules":[string],"negotiation_style":string,"sales_tone":string}。'
            'bottom_line_rules 必须是不可逾越的红线列表。'
        )
        user_prompt = f'商家语音转本：{transcript}\n菜单底价：{json.dumps(normalized_menu, ensure_ascii=False)}'
        parsed = MerchantPersonaLLMOutput.model_validate(await self._ask_json(system_prompt, user_prompt))

        joined_rules = '；'.join(parsed.bottom_line_rules)
        sales_system_prompt = (
            f"你是该商家的 MerchantAgent。商家谈判风格：{parsed.negotiation_style}；销售语气：{parsed.sales_tone}；"
            f"绝对红线：{joined_rules}。菜单底价数据：{json.dumps(normalized_menu, ensure_ascii=False)}。"
            '回复时必须在利润、安全和成交率之间平衡，但绝不能突破红线。'
        )

        record = MerchantPersonaRecord(
            merchant_id=merchant_id,
            transcript=transcript,
            menu_floor_data=normalized_menu,
            bottom_line_rules=parsed.bottom_line_rules,
            negotiation_style=parsed.negotiation_style,
            sales_tone=parsed.sales_tone,
            sales_system_prompt=sales_system_prompt,
            created_at=time.time(),
        )
        await self._save_merchant_record(record)
        return record

    async def _save_merchant_record(self, record: MerchantPersonaRecord) -> None:
        async with session_scope() as session:
            row = await session.get(MerchantORM, record.merchant_id)
            if row is None:
                row = MerchantORM(merchant_id=record.merchant_id)
                session.add(row)
            row.persona_profile = {
                'transcript': record.transcript,
                'menu_floor_data': record.menu_floor_data,
                'negotiation_style': record.negotiation_style,
                'sales_tone': record.sales_tone,
                'created_at': record.created_at,
            }
            row.bottom_line_rules = record.bottom_line_rules
            row.sales_system_prompt = record.sales_system_prompt
            row.updated_at = time.time()
