from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .llm_client import get_llm_client
from .persona_builder import ClientPersonaBuilder, MerchantPersonaBuilder

router = APIRouter(prefix='/api/v1/persona', tags=['Persona Builder'])


class BuildClientPersonaRequest(BaseModel):
    client_id: str
    transcript: str = Field(..., min_length=1)


class BuildMerchantPersonaRequest(BaseModel):
    merchant_id: str
    transcript: str = Field(..., min_length=1)
    menu_floor_data: Dict[str, float] = Field(..., min_length=1)


@router.post('/client/build')
async def build_client_persona(body: BuildClientPersonaRequest) -> Dict[str, Any]:
    try:
        builder = ClientPersonaBuilder(get_llm_client())
        record = await builder.build_from_transcript(body.client_id, body.transcript)
        return record.model_dump()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post('/merchant/build')
async def build_merchant_persona(body: BuildMerchantPersonaRequest) -> Dict[str, Any]:
    try:
        builder = MerchantPersonaBuilder(get_llm_client())
        record = await builder.build_from_transcript(body.merchant_id, body.transcript, body.menu_floor_data)
        return record.model_dump()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
