from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .a2a_arena import A2AArena
from .data_models import ClientORM, MerchantORM
from .db import session_scope
from .llm_client import get_llm_client

router = APIRouter(prefix='/api/v1/a2a/arena', tags=['A2A Arena'])

_arena = A2AArena(get_llm_client())
_arena_tasks: Dict[str, asyncio.Task] = {}
_arena_results: Dict[str, Dict[str, Any]] = {}
_arena_errors: Dict[str, str] = {}


class StartArenaRequest(BaseModel):
    client_id: str
    merchant_id: str
    item_name: str = Field(..., min_length=1)
    buyer_start_price: float = Field(..., gt=0)
    seller_start_price: float = Field(..., gt=0)
    buyer_prompt: str = ''
    seller_prompt: str = ''
    seller_bottom_lines: List[str] = Field(default_factory=list)
    max_turns: int = 4


async def _load_persona_bundle(client_id: str, merchant_id: str) -> tuple[str, str, List[str]]:
    async with session_scope() as session:
        client = await session.get(ClientORM, client_id)
        merchant = await session.get(MerchantORM, merchant_id)
        buyer_prompt = client.buyer_system_prompt if client else ''
        seller_prompt = merchant.sales_system_prompt if merchant else ''
        bottom_lines = list(merchant.bottom_line_rules) if merchant and merchant.bottom_line_rules else []
        return buyer_prompt, seller_prompt, bottom_lines


async def _run_arena_session(session_id: str, body: StartArenaRequest) -> None:
    try:
        buyer_prompt, seller_prompt, seller_bottom_lines = await _load_persona_bundle(body.client_id, body.merchant_id)
        result = await _arena.run(
            session_id=session_id,
            item_name=body.item_name,
            buyer_prompt=body.buyer_prompt or buyer_prompt,
            seller_prompt=body.seller_prompt or seller_prompt,
            seller_bottom_lines=body.seller_bottom_lines or seller_bottom_lines,
            buyer_start_price=body.buyer_start_price,
            seller_start_price=body.seller_start_price,
            max_turns=body.max_turns,
        )
        _arena_results[session_id] = result
    except Exception as exc:
        _arena_errors[session_id] = str(exc)


@router.post('/start')
async def start_a2a_arena(body: StartArenaRequest) -> Dict[str, Any]:
    session_id = f'a2a-{uuid.uuid4().hex[:12]}'
    task = asyncio.create_task(_run_arena_session(session_id, body))
    _arena_tasks[session_id] = task
    return {
        'session_id': session_id,
        'status': 'started',
        'stream_url': f'/api/v1/a2a/arena/stream/{session_id}',
        'ws_url': f'/ws/a2a/arena/{session_id}',
        'result_url': f'/api/v1/a2a/arena/result/{session_id}',
    }


@router.get('/stream/{session_id}')
async def stream_a2a_arena(session_id: str):
    if session_id not in _arena_tasks and session_id not in _arena_results and session_id not in _arena_errors:
        raise HTTPException(status_code=404, detail='session_not_found')

    async def _event_gen():
        async for event in _arena.stream_events(session_id):
            yield f"event: {event['type']}\ndata: {json.dumps(event['payload'], ensure_ascii=False)}\n\n"

    return StreamingResponse(_event_gen(), media_type='text/event-stream')


@router.get('/result/{session_id}')
async def get_a2a_arena_result(session_id: str) -> Dict[str, Any]:
    task = _arena_tasks.get(session_id)
    if task and not task.done():
        return {'session_id': session_id, 'status': 'running'}
    if session_id in _arena_errors:
        raise HTTPException(status_code=500, detail=_arena_errors[session_id])
    if session_id not in _arena_results:
        raise HTTPException(status_code=404, detail='session_not_found')
    return _arena_results[session_id]


@router.websocket('/ws/a2a/arena/{session_id}')
async def ws_a2a_arena(session_id: str, websocket: WebSocket):
    if session_id not in _arena_tasks and session_id not in _arena_results and session_id not in _arena_errors:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        async for event in _arena.stream_events(session_id):
            await websocket.send_text(json.dumps(event, ensure_ascii=False))
    except WebSocketDisconnect:
        return
