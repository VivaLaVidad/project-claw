from __future__ import annotations

import asyncio
import hashlib
import json
import math
import random
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

import requests

from config import settings
from claw_protocol import AgentIdentity, AgentRole, MerchantInfo, TradeRequest, TradeResponse


PERSONA_DIM = 1024


@dataclass
class PersonaProfile:
    user_id: str
    preferences: list[str] = field(default_factory=list)
    social_tags: list[str] = field(default_factory=list)
    social_embedding: list[float] = field(default_factory=list)
    acceptance_history: list[float] = field(default_factory=list)
    memory_vector: list[float] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class PersonaManager:
    """将消费偏好 + 社交标签序列化为本地 1024 维初始记忆。"""

    def __init__(self, store_path: str = "consumer_personas.json"):
        self.store_path = Path(store_path)
        self._profiles: dict[str, PersonaProfile] = {}
        self._load()

    def _load(self) -> None:
        if not self.store_path.exists():
            return
        try:
            raw = json.loads(self.store_path.read_text(encoding="utf-8"))
            for user_id, payload in raw.items():
                self._profiles[user_id] = PersonaProfile(**payload)
        except Exception:
            self._profiles = {}

    def _save(self) -> None:
        payload = {user_id: asdict(profile) for user_id, profile in self._profiles.items()}
        self.store_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _normalize(vector: list[float]) -> list[float]:
        if len(vector) != PERSONA_DIM:
            if len(vector) > PERSONA_DIM:
                vector = vector[:PERSONA_DIM]
            else:
                vector = vector + [0.0] * (PERSONA_DIM - len(vector))
        norm = math.sqrt(sum(x * x for x in vector)) or 1.0
        return [x / norm for x in vector]

    def _encode_tokens(self, preferences: list[str], social_tags: list[str]) -> list[float]:
        vector = [0.0] * PERSONA_DIM
        for idx, token in enumerate(preferences + social_tags):
            token = token.strip()
            if not token:
                continue
            digest = hashlib.sha256(f"{idx}:{token}".encode("utf-8")).digest()
            slot = int.from_bytes(digest[:2], "big") % PERSONA_DIM
            weight = 1.25 if idx < len(preferences) else 0.85
            vector[slot] += weight
        return vector

    def upsert_profile(
        self,
        user_id: str,
        preferences: list[str],
        social_tags: list[str],
        social_embedding: list[float],
    ) -> PersonaProfile:
        token_vec = self._encode_tokens(preferences, social_tags)
        embedding = self._normalize(list(social_embedding))
        memory = self._normalize([token_vec[i] + embedding[i] for i in range(PERSONA_DIM)])
        profile = self._profiles.get(user_id) or PersonaProfile(user_id=user_id)
        profile.preferences = preferences
        profile.social_tags = social_tags
        profile.social_embedding = embedding
        profile.memory_vector = memory
        profile.updated_at = time.time()
        self._profiles[user_id] = profile
        self._save()
        return profile

    def get_profile(self, user_id: str) -> Optional[PersonaProfile]:
        return self._profiles.get(user_id)

    def record_acceptance(self, user_id: str, accepted_price_ratio: float) -> None:
        profile = self._profiles.get(user_id)
        if not profile:
            return
        profile.acceptance_history.append(max(0.0, min(2.0, accepted_price_ratio)))
        profile.acceptance_history = profile.acceptance_history[-24:]
        profile.updated_at = time.time()
        self._save()


class LedgerServiceClient:
    """任务开始前做 Zero-Trust 预充值校验。"""

    def __init__(self, base_url: str = "", bearer_token: str = "", timeout_sec: float = 6.0):
        self.base_url = base_url.rstrip("/")
        self.bearer_token = bearer_token
        self.timeout_sec = timeout_sec

    async def check_balance(self, merchant_or_user_id: str, required_balance: float = 1.0) -> dict:
        if not self.base_url:
            return {"ok": True, "can_start": True, "balance": required_balance, "mocked": True}

        def _call() -> dict:
            headers = {"Authorization": f"Bearer {self.bearer_token}"} if self.bearer_token else {}
            resp = requests.get(f"{self.base_url}/api/v1/ledger/status", headers=headers, timeout=self.timeout_sec)
            resp.raise_for_status()
            data = resp.json()
            return {
                "ok": True,
                "can_start": bool(data.get("can_quote", False)) and float(data.get("balance", 0.0)) >= required_balance,
                "balance": float(data.get("balance", 0.0)),
                "payload": data,
                "subject_id": merchant_or_user_id,
            }

        try:
            return await asyncio.wait_for(asyncio.to_thread(_call), timeout=self.timeout_sec + 1)
        except Exception as e:
            return {"ok": False, "can_start": False, "balance": 0.0, "error": str(e), "subject_id": merchant_or_user_id}


class BargainAgent:
    """基于用户接受历史自动设定 target_price，并对 Offer 做 Top-1 评分。"""

    def __init__(self, persona_manager: PersonaManager):
        self.persona_manager = persona_manager

    @staticmethod
    def _pref_bonus(profile: PersonaProfile) -> float:
        bonus = 1.0
        prefs = " ".join(profile.preferences + profile.social_tags)
        if "价格敏感" in prefs or "省钱" in prefs:
            bonus -= 0.08
        if "喜欢吃辣" in prefs or "重口" in prefs:
            bonus += 0.03
        if "品质优先" in prefs or "高评分" in prefs:
            bonus += 0.05
        return max(0.82, min(1.18, bonus))

    def derive_target_price(self, user_id: str, anchor_price: float) -> float:
        profile = self.persona_manager.get_profile(user_id)
        if not profile:
            return round(anchor_price, 2)
        history = profile.acceptance_history[-6:]
        history_factor = sum(history) / len(history) if history else 1.0
        target = anchor_price * history_factor * self._pref_bonus(profile)
        return round(max(anchor_price * 0.72, min(anchor_price * 1.15, target)), 2)

    def build_trade_request(
        self,
        user_id: str,
        item_name: str,
        anchor_price: float,
        max_distance: float = 5000.0,
        ttl_seconds: int = 30,
    ) -> TradeRequest:
        target_price = self.derive_target_price(user_id, anchor_price)
        return TradeRequest(
            buyer_id=user_id,
            item_name=item_name,
            target_price=target_price,
            max_distance=max_distance,
            ttl_seconds=ttl_seconds,
        )

    def score_offer(self, profile: Optional[PersonaProfile], offer: TradeResponse) -> float:
        merchant = offer.merchant_info or MerchantInfo(merchant_name="unknown", rating=4.2, distance_m=1200.0)
        offered_price = float(offer.counter_offer_price or 0.0)
        rating_score = (merchant.rating / 5.0) * 0.25
        distance_score = max(0.0, 1.0 - min(merchant.distance_m, 5000.0) / 5000.0) * 0.20
        accept_score = 0.35 if offer.is_accepted else 0.18
        price_pref = 1.0
        if profile:
            price_pref = 1.08 if any("价格敏感" in t or "省钱" in t for t in profile.preferences + profile.social_tags) else 0.96
        price_score = max(0.0, 1.0 - offered_price / 50.0) * 0.20 * price_pref
        freshness_score = max(0.0, 1.0 - (time.time() - offer.timestamp) / 120.0) * 0.10
        return round(rating_score + distance_score + accept_score + price_score + freshness_score, 4)

    def pick_top1(self, user_id: str, offers: list[TradeResponse]) -> Optional[TradeResponse]:
        if not offers:
            return None
        profile = self.persona_manager.get_profile(user_id)
        ranked = sorted(offers, key=lambda offer: self.score_offer(profile, offer), reverse=True)
        chosen = ranked[0]
        if chosen.counter_offer_price:
            self.persona_manager.record_acceptance(user_id, chosen.counter_offer_price / max(1.0, chosen.counter_offer_price))
        return chosen


class SocialHandshake:
    def __init__(self, threshold: float = 0.85):
        self.threshold = threshold

    @staticmethod
    def cosine_similarity(a: list[float], b: list[float]) -> float:
        if not a or not b:
            return 0.0
        size = min(len(a), len(b), PERSONA_DIM)
        dot = sum(a[i] * b[i] for i in range(size))
        norm_a = math.sqrt(sum(a[i] * a[i] for i in range(size))) or 1.0
        norm_b = math.sqrt(sum(b[i] * b[i] for i in range(size))) or 1.0
        return dot / (norm_a * norm_b)

    def break_ice_tip(self, tags_a: list[str], tags_b: list[str]) -> str:
        overlap = list({*tags_a}.intersection(tags_b))
        if overlap:
            topic = overlap[0]
            return f"你俩都对“{topic}”有明显偏好，可以从这个共同点开场：‘你也好这口？’"
        return random.choice([
            "你们俩画像很接近，可以从‘今天想吃点狠的还是清爽的’破冰。",
            "你们俩的社交标签高度相似，建议先聊最近常点的夜宵。",
            "相似度很高，先从口味偏好切入，破冰成功率最高。",
        ])

    def handshake(self, left: PersonaProfile, right: PersonaProfile, left_identity: AgentIdentity, right_identity: AgentIdentity) -> dict:
        score = self.cosine_similarity(left.memory_vector, right.memory_vector)
        matched = score >= self.threshold
        return {
            "matched": matched,
            "score": round(score, 4),
            "left_agent_id": left_identity.agent_id,
            "right_agent_id": right_identity.agent_id,
            "tip": self.break_ice_tip(left.social_tags, right.social_tags) if matched else "相似度不足，继续普通撮合。",
        }


class ConsumerAgent:
    def __init__(
        self,
        user_id: str,
        persona_manager: PersonaManager,
        ledger_client: Optional[LedgerServiceClient] = None,
        bargain_agent: Optional[BargainAgent] = None,
        handshake: Optional[SocialHandshake] = None,
        signaling_base_url: str = settings.signaling_http_base_url,
    ):
        self.user_id = user_id
        self.identity = AgentIdentity(agent_id=user_id, role=AgentRole.BUYER, name=f"consumer-{user_id[:6]}")
        self.persona_manager = persona_manager
        self.ledger_client = ledger_client or LedgerServiceClient()
        self.bargain_agent = bargain_agent or BargainAgent(persona_manager)
        self.handshake_engine = handshake or SocialHandshake()
        self.signaling_base_url = signaling_base_url.rstrip("/")

    async def start_trade(self, item_name: str, anchor_price: float, required_balance: float = 1.0) -> dict:
        balance = await self.ledger_client.check_balance(self.user_id, required_balance=required_balance)
        if not balance.get("can_start"):
            return {"ok": False, "stage": "precheck", "reason": "zero_trust_balance_check_failed", "ledger": balance}
        request = self.bargain_agent.build_trade_request(self.user_id, item_name, anchor_price)
        return {"ok": True, "stage": "request_created", "ledger": balance, "request": request}

    async def request_real_offers(self, item_name: str, anchor_price: float, location: str = "匿名商圈", timeout: float = 3.0) -> dict:
        boot = await self.start_trade(item_name=item_name, anchor_price=anchor_price)
        if not boot.get("ok"):
            return boot
        request: TradeRequest = boot["request"]

        def _call() -> dict:
            resp = requests.post(
                f"{self.signaling_base_url}/intent",
                json={
                    "client_id": self.user_id,
                    "location": location,
                    "demand_text": f"想吃{item_name}",
                    "max_price": request.target_price,
                    "timeout": timeout,
                },
                timeout=max(5.0, timeout + 2),
            )
            resp.raise_for_status()
            return resp.json()

        try:
            payload = await asyncio.wait_for(asyncio.to_thread(_call), timeout=max(6.0, timeout + 3))
        except Exception as e:
            return {"ok": False, "stage": "signaling", "error": str(e), "request": request}

        offers = [self._normalize_offer(request, row) for row in payload.get("offers", [])]
        best = self.select_best_offer(offers)
        return {
            "ok": True,
            "stage": "offers_received",
            "request": request,
            "raw_payload": payload,
            "offers": offers,
            "best_offer": best,
        }

    def _normalize_offer(self, request: TradeRequest, row: dict[str, Any]) -> TradeResponse:
        merchant_id = str(row.get("merchant_id", "unknown"))
        price = float(row.get("final_price", 0.0) or 0.0)
        return TradeResponse(
            request_id=request.request_id,
            seller_id=merchant_id,
            is_accepted=True,
            counter_offer_price=price,
            merchant_info=MerchantInfo(
                merchant_name=merchant_id,
                distance_m=float(row.get("distance_m", 800.0) or 800.0),
                rating=min(5.0, max(0.0, float(row.get("rating", 4.7) or 4.7))),
            ),
            reason=str(row.get("reply_text", "")),
        )

    async def run_sandbox(self, merchant_id: str, item_name: str, target_price: float) -> dict:
        def _call() -> dict:
            resp = requests.post(
                f"{self.signaling_base_url}/sandbox/match",
                json={
                    "client_id": self.user_id,
                    "merchant_id": merchant_id,
                    "item": item_name,
                    "target": target_price,
                },
                timeout=8,
            )
            resp.raise_for_status()
            return resp.json()

        try:
            return await asyncio.wait_for(asyncio.to_thread(_call), timeout=9)
        except Exception as e:
            return {"ok": False, "stage": "sandbox", "error": str(e)}

    async def run_real_closed_loop(self, item_name: str, anchor_price: float, location: str = "匿名商圈") -> dict:
        flow = await self.request_real_offers(item_name=item_name, anchor_price=anchor_price, location=location)
        if not flow.get("ok"):
            return flow
        best: TradeResponse | None = flow.get("best_offer")
        if not best:
            flow["sandbox"] = None
            flow["final_selection"] = None
            return flow
        sandbox = await self.run_sandbox(
            merchant_id=best.seller_id,
            item_name=item_name,
            target_price=float(best.counter_offer_price or anchor_price),
        )
        flow["sandbox"] = sandbox
        flow["final_selection"] = {
            "merchant_id": best.seller_id,
            "final_price": float(best.counter_offer_price or 0.0),
            "reply_text": best.reason,
        }
        return flow

    def select_best_offer(self, offers: list[TradeResponse]) -> Optional[TradeResponse]:
        return self.bargain_agent.pick_top1(self.user_id, offers)

    def social_handshake(self, peer_user_id: str) -> dict:
        me = self.persona_manager.get_profile(self.user_id)
        peer = self.persona_manager.get_profile(peer_user_id)
        if not me or not peer:
            return {"matched": False, "score": 0.0, "tip": "画像信息不足，无法触发破冰建议。"}
        peer_identity = AgentIdentity(agent_id=peer_user_id, role=AgentRole.BUYER, name=f"consumer-{peer_user_id[:6]}")
        return self.handshake_engine.handshake(me, peer, self.identity, peer_identity)


async def demo_consumer_flow() -> dict:
    manager = PersonaManager()
    alice = manager.upsert_profile(
        user_id="consumer-alice",
        preferences=["喜欢吃辣", "对价格敏感"],
        social_tags=["夜猫子", "川渝口味", "电竞"],
        social_embedding=[0.3] * PERSONA_DIM,
    )
    manager.upsert_profile(
        user_id="consumer-bob",
        preferences=["喜欢吃辣", "夜宵党"],
        social_tags=["川渝口味", "电竞", "社牛"],
        social_embedding=[0.29] * PERSONA_DIM,
    )
    agent = ConsumerAgent(user_id=alice.user_id, persona_manager=manager)
    trade = await agent.start_trade(item_name="麻辣烫", anchor_price=18.0)
    peer = agent.social_handshake("consumer-bob")
    return {"trade": trade, "peer": peer}


if __name__ == "__main__":
    print(asyncio.run(demo_consumer_flow()))
