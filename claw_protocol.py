"""claw_protocol.py - Project Claw A2A Protocol
Buyer/Seller Agent auto-negotiation schema and engine.
"""
from __future__ import annotations
import asyncio, hashlib, json, logging, time, uuid
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger("claw.protocol")


class AgentRole(str, Enum):
    BUYER  = "buyer"
    SELLER = "seller"


class NegotiationStatus(str, Enum):
    PENDING   = "pending"
    ACCEPTED  = "accepted"
    REJECTED  = "rejected"
    COUNTERED = "countered"
    FAILED    = "failed"


class AgentIdentity(BaseModel):
    """Agent identity - contains agent_id, role, public_key."""
    agent_id:   str       = Field(default_factory=lambda: str(uuid.uuid4()))
    role:       AgentRole
    public_key: str       = Field(default="", description="reserved for ECDSA signing")
    name:       str       = Field(default="")
    created_at: float     = Field(default_factory=time.time)

    @field_validator("public_key", mode="before")
    @classmethod
    def _fill_key(cls, v: str) -> str:
        return v or hashlib.sha256(str(uuid.uuid4()).encode()).hexdigest()[:32]

    def short_id(self) -> str:
        return self.agent_id[:8]


class TradeRequest(BaseModel):
    """Buyer broadcasts this to nearby sellers."""
    request_id:   str   = Field(default_factory=lambda: str(uuid.uuid4()))
    buyer_id:     str
    item_name:    str   = Field(..., min_length=1, max_length=50)
    target_price: float = Field(..., gt=0, description="buyer desired price")
    max_distance: float = Field(default=5000.0, description="meters")
    timestamp:    float = Field(default_factory=time.time)
    ttl_seconds:  int   = Field(default=30)

    @property
    def is_expired(self) -> bool:
        return time.time() - self.timestamp > self.ttl_seconds

    def summary(self) -> str:
        return (f"TradeRequest[{self.request_id[:8]}] "
                f"buyer={self.buyer_id[:8]} "
                f"item={self.item_name} target={self.target_price}")


class MerchantInfo(BaseModel):
    """Attached to TradeResponse."""
    merchant_name: str
    address:       str   = ""
    distance_m:    float = 0.0
    rating:        float = Field(default=5.0, ge=0.0, le=5.0)


class TradeResponse(BaseModel):
    """Seller reply to a TradeRequest."""
    response_id:         str            = Field(default_factory=lambda: str(uuid.uuid4()))
    request_id:          str
    seller_id:           str
    is_accepted:         bool
    counter_offer_price: Optional[float] = Field(default=None)
    valid_until:         float           = Field(default_factory=lambda: time.time() + 60)
    merchant_info:       Optional[MerchantInfo] = None
    reason:              str   = ""
    timestamp:           float = Field(default_factory=time.time)

    @property
    def is_expired(self) -> bool:
        return time.time() > self.valid_until

    def summary(self) -> str:
        s = "ACCEPTED" if self.is_accepted else f"COUNTER={self.counter_offer_price}"
        return f"TradeResponse[{self.response_id[:8]}] seller={self.seller_id[:8]} {s}"


class NegotiationLog(BaseModel):
    """Single round log entry."""
    round_num:    int
    buyer_id:     str
    seller_id:    str
    buyer_price:  float
    seller_price: float
    gap:          float
    status:       NegotiationStatus
    message:      str
    timestamp:    float = Field(default_factory=time.time)


class NegotiationSession(BaseModel):
    """Full negotiation session record."""
    session_id:  str   = Field(default_factory=lambda: str(uuid.uuid4()))
    buyer_id:    str
    seller_id:   str
    item_name:   str
    initial_ask: float
    floor_price: float
    final_price: Optional[float]      = None
    status:      NegotiationStatus    = NegotiationStatus.PENDING
    rounds:      List[NegotiationLog] = Field(default_factory=list)
    started_at:  float = Field(default_factory=time.time)
    finished_at: Optional[float] = None

    def add_round(self, log: NegotiationLog) -> None:
        self.rounds.append(log)

    def finish(self, status: NegotiationStatus, final_price: float = None) -> None:
        self.status      = status
        self.final_price = final_price
        self.finished_at = time.time()


# ===== Inventory =====

_FLOOR: Dict[str, float]  = {
    "niurou": 12.0, "mala": 9.0, "shuijiao": 5.0,
    "chaofan": 8.0, "liangpi": 6.0, "setA": 18.0, "setB": 22.0,
}
_NORMAL: Dict[str, float] = {
    "niurou": 18.0, "mala": 15.0, "shuijiao": 8.0,
    "chaofan": 12.0, "liangpi": 10.0, "setA": 25.0, "setB": 30.0,
}

# Chinese alias -> internal key
_ALIAS: Dict[str, str] = {
    "\u725b\u8089\u9762": "niurou",
    "\u9ebb\u8fa3\u70eb": "mala",
    "\u6c34\u9975": "shuijiao",
    "\u7092\u996d": "chaofan",
    "\u51c9\u76ae": "liangpi",
    "\u5957\u9910A": "setA",
    "\u5957\u9910B": "setB",
}


def _resolve(item_name: str) -> str:
    """Resolve Chinese name or internal key."""
    return _ALIAS.get(item_name, item_name)


class A2ANegotiator:
    """A2A negotiation engine."""

    def __init__(
        self,
        identity: AgentIdentity,
        floor_prices: Dict[str, float] = None,
        normal_prices: Dict[str, float] = None,
        max_rounds: int = 5,
        concession_rate: float = 0.05,
        ws_host: str = "127.0.0.1",
        ws_port: int = 9100,
    ) -> None:
        self.identity        = identity
        self.floor_prices    = floor_prices  or _FLOOR
        self.normal_prices   = normal_prices or _NORMAL
        self.max_rounds      = max_rounds
        self.concession_rate = concession_rate
        self.ws_host         = ws_host
        self.ws_port         = ws_port
        self.sessions: Dict[str, NegotiationSession] = {}
        logger.info(f"[A2ANegotiator] id={identity.short_id()} role={identity.role.value}")

    async def broadcast_intent(
        self,
        item_name: str,
        target_price: float,
        max_distance: float = 5000.0,
        ttl_seconds: int = 30,
    ) -> TradeRequest:
        """Buyer broadcasts a TradeRequest."""
        if self.identity.role != AgentRole.BUYER:
            raise ValueError("Only BUYER can broadcast trade intent")
        req = TradeRequest(
            buyer_id=self.identity.agent_id,
            item_name=item_name,
            target_price=target_price,
            max_distance=max_distance,
            ttl_seconds=ttl_seconds,
        )
        logger.info(f"[A2A] BROADCAST | {req.summary()}")
        return req

    async def evaluate_offer(
        self,
        request: TradeRequest,
        seller_identity: AgentIdentity,
        merchant_name: str = "LobsterShop",
    ) -> TradeResponse:
        """Seller evaluates against floor price. ask>=floor accept, else counter."""
        if request.is_expired:
            logger.warning(f"[A2A] EXPIRED {request.request_id[:8]}")
            return TradeResponse(
                request_id=request.request_id,
                seller_id=seller_identity.agent_id,
                is_accepted=False, reason="request expired",
            )
        key   = _resolve(request.item_name)
        ask   = request.target_price
        floor = self.floor_prices.get(key)
        if floor is None:
            logger.warning(f"[A2A] UNKNOWN item: {request.item_name}")
            return TradeResponse(
                request_id=request.request_id,
                seller_id=seller_identity.agent_id,
                is_accepted=False, reason=f"item not found: {request.item_name}",
            )
        info = MerchantInfo(merchant_name=merchant_name, distance_m=100.0, rating=4.8)
        if ask >= floor:
            logger.info(f"[A2A] ACCEPTED item={request.item_name} ask={ask} floor={floor}")
            return TradeResponse(
                request_id=request.request_id,
                seller_id=seller_identity.agent_id,
                is_accepted=True, counter_offer_price=ask,
                merchant_info=info, reason="price acceptable",
            )
        counter = round(floor * 1.10, 1)
        gap     = round(floor - ask, 2)
        logger.warning(
            f"[A2A] REJECTED Agent {request.buyer_id[:8]} <-> "
            f"Agent {seller_identity.short_id()} "
            f"bargain failed, price gap {gap}, counter={counter}"
        )
        return TradeResponse(
            request_id=request.request_id,
            seller_id=seller_identity.agent_id,
            is_accepted=False, counter_offer_price=counter,
            merchant_info=info, reason=f"below cost, min {counter}",
        )

    async def negotiate(
        self,
        request: TradeRequest,
        seller: "A2ANegotiator",
    ) -> NegotiationSession:
        """Multi-round auto-bargaining."""
        key         = _resolve(request.item_name)
        floor       = seller.floor_prices.get(key, 0.0)
        buyer_price = request.target_price
        sell_price  = seller.normal_prices.get(key, floor * 1.5)
        session = NegotiationSession(
            buyer_id=self.identity.agent_id,
            seller_id=seller.identity.agent_id,
            item_name=request.item_name,
            initial_ask=buyer_price,
            floor_price=floor,
        )
        self.sessions[session.session_id] = session
        logger.info(
            f"[A2A] NEGOTIATE buyer={self.identity.short_id()} "
            f"seller={seller.identity.short_id()} "
            f"item={request.item_name} ask={buyer_price} list={sell_price}"
        )
        for rnd in range(1, self.max_rounds + 1):
            cur = TradeRequest(
                buyer_id=request.buyer_id,
                item_name=request.item_name,
                target_price=round(buyer_price, 2),
                ttl_seconds=60,
            )
            resp = await seller.evaluate_offer(cur, seller.identity)
            if resp.is_accepted:
                msg = (
                    f"Agent {self.identity.short_id()} <-> "
                    f"Agent {seller.identity.short_id()} "
                    f"round {rnd} DEAL at {buyer_price:.1f}"
                )
                logger.info(f"[A2A] DEAL | {msg}")
                session.add_round(NegotiationLog(
                    round_num=rnd,
                    buyer_id=self.identity.agent_id,
                    seller_id=seller.identity.agent_id,
                    buyer_price=buyer_price, seller_price=sell_price,
                    gap=0.0, status=NegotiationStatus.ACCEPTED, message=msg,
                ))
                session.finish(NegotiationStatus.ACCEPTED, buyer_price)
                return session
            counter    = resp.counter_offer_price or sell_price
            gap        = round(counter - buyer_price, 2)
            msg = (
                f"Agent {self.identity.short_id()} <-> "
                f"Agent {seller.identity.short_id()} "
                f"bargain failed, price gap {gap} "
                f"(buyer={buyer_price:.1f} counter={counter:.1f})"
            )
            logger.warning(f"[A2A] Round {rnd}/{self.max_rounds} | {msg}")
            session.add_round(NegotiationLog(
                round_num=rnd,
                buyer_id=self.identity.agent_id,
                seller_id=seller.identity.agent_id,
                buyer_price=buyer_price, seller_price=counter,
                gap=gap, status=NegotiationStatus.COUNTERED, message=msg,
            ))
            buyer_price = round(buyer_price * (1 + self.concession_rate), 2)
            sell_price  = round(sell_price  * (1 - self.concession_rate * 0.5), 2)
        final_gap = round(seller.floor_prices.get(key, 0) - request.target_price, 2)
        fail_msg  = (
            f"Agent {self.identity.short_id()} <-> "
            f"Agent {seller.identity.short_id()} "
            f"{self.max_rounds} rounds failed, total gap {final_gap}"
        )
        logger.error(f"[A2A] FAILED | {fail_msg}")
        session.finish(NegotiationStatus.FAILED)
        return session


def create_ws_app(negotiator: A2ANegotiator):
    """FastAPI + WebSocket listener."""
    try:
        from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    except ImportError:
        logger.error("fastapi not installed: pip install fastapi uvicorn")
        return None
    app = FastAPI(title="Claw A2A", version="1.0")
    _conns: Dict[str, object] = {}

    @app.websocket("/ws/{agent_id}")
    async def ws_ep(websocket: WebSocket, agent_id: str):
        await websocket.accept()
        _conns[agent_id] = websocket
        logger.info(f"[WS] connected: {agent_id[:8]}")
        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    req  = TradeRequest(**json.loads(raw))
                    resp = await negotiator.evaluate_offer(req, negotiator.identity)
                    await websocket.send_text(resp.model_dump_json())
                except Exception as e:
                    await websocket.send_text(json.dumps({"error": str(e)}))
        except WebSocketDisconnect:
            _conns.pop(agent_id, None)

    @app.get("/health")
    async def health():
        return {"status": "ok", "agent_id": negotiator.identity.agent_id,
                "sessions": len(negotiator.sessions)}

    return app


def make_buyer(name: str = "Buyer", ws_port: int = 9100) -> A2ANegotiator:
    return A2ANegotiator(identity=AgentIdentity(role=AgentRole.BUYER, name=name), ws_port=ws_port)


def make_seller(
    name: str = "LobsterShop",
    floor_prices: Dict[str, float] = None,
    normal_prices: Dict[str, float] = None,
    ws_port: int = 9101,
) -> A2ANegotiator:
    return A2ANegotiator(
        identity=AgentIdentity(role=AgentRole.SELLER, name=name),
        floor_prices=floor_prices, normal_prices=normal_prices, ws_port=ws_port,
    )


async def _demo():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    buyer  = make_buyer(name="XiaoWang")
    seller = make_seller(name="LobsterShop")
    cases = [
        ("niurou",  16.0, "above floor -> deal"),
        ("mala",     8.0, "below floor -> bargain"),
        ("shuijiao", 6.0, "above floor -> deal"),
        ("liangpi",  4.0, "far below -> fail"),
        ("unknown", 10.0, "unknown item"),
    ]
    print("\n" + "=" * 55 + "\nClaw A2A Protocol Demo\n" + "=" * 55)
    for item, price, desc in cases:
        print(f"\n[{desc}] item={item} ask={price}")
        req     = await buyer.broadcast_intent(item, price, ttl_seconds=60)
        session = await buyer.negotiate(req, seller)
        fp      = f" final={session.final_price}" if session.final_price else ""
        print(f"  -> {session.status.value}{fp} ({len(session.rounds)} rounds)")
    print("\nDemo done.")


if __name__ == "__main__":
    asyncio.run(_demo())
