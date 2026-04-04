from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from edge_box.local_memory import get_session_manager

from .data_models import ClientORM, MerchantORM
from .db import session_scope
from .langgraph_multi_agent import MultiAgentNegotiationCluster


class ClientProfile(BaseModel):
    """C端用户画像。"""

    client_id: str
    price_sensitivity: float
    time_urgency: float
    quality_preference: float
    brand_preferences: List[str] = Field(default_factory=list)
    purchase_history: List[Dict[str, Any]] = Field(default_factory=list)
    location: str = ""
    created_at: float = Field(default_factory=time.time)


class MerchantProfile(BaseModel):
    """B端商家画像。"""

    merchant_id: str
    shop_name: str
    inventory: Dict[str, int] = Field(default_factory=dict)
    pricing_strategy: str = "normal"
    service_rating: float = 5.0
    response_speed: float = 1.0
    negotiation_style: str = "friendly"
    created_at: float = Field(default_factory=time.time)


class DialogueTurn(BaseModel):
    """对话轮次。"""

    session_id: str
    turn_id: int
    speaker: str
    text: str
    timestamp: float
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DialogueSession(BaseModel):
    """对话会话。"""

    session_id: str
    client_id: str
    merchant_id: str
    item_name: str
    expected_price: float
    turns: List[DialogueTurn] = Field(default_factory=list)
    status: str = "active"
    best_offer: Optional[Dict[str, Any]] = None
    created_at: float = Field(default_factory=time.time)


class DialogueManager:
    """基于 LangGraph 的多智能体对话管理器。"""

    def __init__(self, llm_client: Any):
        self.llm_client = llm_client
        self.sessions: Dict[str, DialogueSession] = {}
        self.client_profiles: Dict[str, ClientProfile] = {}
        self.merchant_profiles: Dict[str, MerchantProfile] = {}
        self.cluster = MultiAgentNegotiationCluster(
            llm_client=llm_client,
            agents_dir=Path(__file__).resolve().parent.parent / "agents",
        )
        self.session_manager = get_session_manager()

    async def start_dialogue(
        self,
        session_id: str,
        client_id: str,
        merchant_id: str,
        item_name: str,
        expected_price: float,
        client_profile: ClientProfile,
        merchant_profile: MerchantProfile,
    ) -> DialogueSession:
        session = DialogueSession(
            session_id=session_id,
            client_id=client_id,
            merchant_id=merchant_id,
            item_name=item_name,
            expected_price=expected_price,
        )
        self.sessions[session_id] = session
        self.client_profiles[client_id] = client_profile
        self.merchant_profiles[merchant_id] = merchant_profile
        self.session_manager.create_session(session_id=session_id, user_id=client_id)
        await self._run_cluster(session_id=session_id, max_rounds=6)
        return self.sessions[session_id]

    async def continue_dialogue(self, session_id: str, max_turns: int = 5) -> DialogueSession:
        session = self.sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        if session.status != "active":
            return session
        await self._run_cluster(session_id=session_id, max_rounds=max(2, max_turns))
        return self.sessions[session_id]

    async def close_session(self, session_id: str) -> bool:
        session = self.sessions.get(session_id)
        if not session:
            return False
        if session.status == "active":
            session.status = "completed"
        await self.session_manager.recycle_session(session_id)
        return True

    def get_session(self, session_id: str) -> Optional[DialogueSession]:
        return self.sessions.get(session_id)

    def get_session_history(self, session_id: str) -> List[Dict[str, Any]]:
        session = self.sessions.get(session_id)
        if not session:
            return []
        return [
            {
                "turn_id": turn.turn_id,
                "speaker": turn.speaker,
                "text": turn.text,
                "timestamp": turn.timestamp,
                "metadata": turn.metadata,
            }
            for turn in session.turns
        ]

    async def _run_cluster(self, session_id: str, max_rounds: int) -> None:
        session = self.sessions[session_id]
        client_profile = self.client_profiles[session.client_id]
        merchant_profile = self.merchant_profiles[session.merchant_id]
        priority_context = self.session_manager.build_priority_context(session.client_id)
        buyer_system_prompt, sales_system_prompt, bottom_line_rules = await self._load_persona_prompts(
            client_id=session.client_id,
            merchant_id=session.merchant_id,
        )

        result = await self.cluster.run(
            session_id=session.session_id,
            client_id=session.client_id,
            merchant_id=session.merchant_id,
            item_name=session.item_name,
            expected_price=session.expected_price,
            client_profile={
                **client_profile.model_dump(),
                "buyer_system_prompt": buyer_system_prompt,
            },
            merchant_profile={
                **merchant_profile.model_dump(),
                "sales_system_prompt": sales_system_prompt,
                "bottom_line_rules": bottom_line_rules,
            },
            priority_context=priority_context,
            max_rounds=max_rounds,
        )

        turns: List[DialogueTurn] = []
        for idx, event in enumerate(result.get("transcript", [])):
            speaker = str(event.get("speaker", "system"))
            text = str(event.get("message", ""))
            turns.append(DialogueTurn(
                session_id=session.session_id,
                turn_id=idx,
                speaker=speaker,
                text=text,
                timestamp=float(event.get("timestamp", time.time())),
                metadata={
                    "price": event.get("price"),
                    "thought": event.get("thought", ""),
                    "action": event.get("action", ""),
                    "gap": event.get("gap"),
                    "decision": event.get("decision"),
                    "resistance": event.get("resistance", ""),
                },
            ))
            role = "client" if speaker == "buyer_agent" else ("merchant" if speaker == "merchant_agent" else "system")
            if text:
                self.session_manager.append_turn(session.session_id, role, text)

        session.turns = turns
        session.status = str(result.get("status", "failed"))
        if result.get("final_deal"):
            session.best_offer = {
                "price": result.get("deal_price"),
                "gap": result.get("final_gap"),
                "agreement": True,
            }
            await self.session_manager.recycle_session(session.session_id)
        elif session.status != "active":
            session.best_offer = {
                "price": result.get("merchant_offer"),
                "gap": result.get("final_gap"),
                "agreement": False,
            }
            await self.session_manager.recycle_session(session.session_id)




    async def _load_persona_prompts(self, client_id: str, merchant_id: str) -> Tuple[str, str, List[str]]:
        async with session_scope() as session:
            client = await session.get(ClientORM, client_id)
            merchant = await session.get(MerchantORM, merchant_id)
            buyer_system_prompt = client.buyer_system_prompt if client else ""
            sales_system_prompt = merchant.sales_system_prompt if merchant else ""
            bottom_line_rules = list(merchant.bottom_line_rules) if merchant and merchant.bottom_line_rules else []
            return buyer_system_prompt, sales_system_prompt, bottom_line_rules


