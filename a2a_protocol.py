"""
Project Claw v13.0 - a2a_protocol.py
CLAP (Claw Lightweight Agent Protocol) v2.0

架构：去中心化设备端撮合

  [龙虾盒子 A]                    [龙虾盒子 B]
  LocalMatchNode  <-- WebSocket -->  LocalMatchNode
       |                                  |
  BusinessBrain                      MatchEngine
  (本地评分，数据不出设备)            (本地评分)

  云端 FastAPI 只做信令转发（Signaling Server）
  对话明文不经过云端。
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, Optional, Callable

logger = logging.getLogger("claw.a2a")


# ==================== CLAP Schema v2.0 ====================

class MessageType(str, Enum):
    HANDSHAKE      = "handshake"
    HANDSHAKE_ACK  = "handshake_ack"
    QUERY          = "query"
    RESPONSE       = "response"
    NEGOTIATE      = "negotiate"
    MATCH_REQ      = "match_req"
    MATCH_RESP     = "match_resp"
    HEARTBEAT      = "heartbeat"
    ERROR          = "error"
    TRADE_REQUEST  = "trade_request"   # v2.0: 发起交易撮合
    TRADE_RESPONSE = "trade_response"  # v2.0: 返回撮合结果
    SIGNAL         = "signal"          # v2.0: 信令（云端转发）


class StatusCode(int, Enum):
    OK           = 200
    ACCEPTED     = 202
    REJECTED     = 203
    BAD_REQUEST  = 400
    UNAUTHORIZED = 401
    NOT_FOUND    = 404
    SERVER_ERROR = 500


@dataclass
class CLAPMessage:
    msg_type:     MessageType
    sender_id:    str
    receiver_id:  str
    payload:      Dict[str, Any] = field(default_factory=dict)
    status:       StatusCode     = StatusCode.OK
    reply_to:     Optional[str]  = None
    msg_id:       str   = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp:    float = field(default_factory=time.time)
    clap_version: str   = "2.0"

    def to_json(self) -> str:
        d = asdict(self)
        d["msg_type"] = self.msg_type.value
        d["status"]   = self.status.value
        return json.dumps(d, ensure_ascii=False)

    @staticmethod
    def from_json(raw: str) -> "CLAPMessage":
        d = json.loads(raw)
        return CLAPMessage(
            msg_type     = MessageType(d["msg_type"]),
            sender_id    = d["sender_id"],
            receiver_id  = d["receiver_id"],
            payload      = d.get("payload", {}),
            status       = StatusCode(d.get("status", 200)),
            reply_to     = d.get("reply_to"),
            msg_id       = d.get("msg_id", str(uuid.uuid4())),
            timestamp    = d.get("timestamp", time.time()),
            clap_version = d.get("clap_version", "2.0"),
        )

    def make_reply(self, msg_type: MessageType,
                   payload: Dict[str, Any],
                   status: StatusCode = StatusCode.OK) -> "CLAPMessage":
        return CLAPMessage(
            msg_type    = msg_type,
            sender_id   = self.receiver_id,
            receiver_id = self.sender_id,
            payload     = payload,
            status      = status,
            reply_to    = self.msg_id,
        )


# ==================== TradeRequest / TradeResponse ====================

@dataclass
class TradeRequest:
    requester_id:     str
    customer_id:      str
    customer_profile: str
    menu_context:     str   = ""
    max_rounds:       int   = 5
    threshold:        float = 75.0
    request_id:       str   = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp:        float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "TradeRequest":
        fields = TradeRequest.__dataclass_fields__.keys()
        return TradeRequest(**{k: v for k, v in d.items() if k in fields})


@dataclass
class TradeResponse:
    request_id:   str
    responder_id: str
    status:       str    # 'accepted' | 'rejected' | 'error'
    score:        float
    summary:      str
    duration:     float
    timestamp:    float = field(default_factory=time.time)

    @property
    def accepted(self) -> bool:
        return self.status == "accepted"

    def to_dict(self) -> dict:
        return asdict(self)


# ==================== LocalMatchNode ====================

class LocalMatchNode:
    """
    设备端 P2P 撮合节点（WebSocket）
    Server 接收 TradeRequest，本地 MatchEngine 评分，返回 TradeResponse。
    云端只转发信令，对话明文不上云。
    """

    def __init__(self, node_id, host="0.0.0.0", port=9100,
                 match_engine=None, on_accepted=None, on_rejected=None):
        self.node_id      = node_id
        self.host         = host
        self.port         = port
        self.match_engine = match_engine
        self.on_accepted  = on_accepted or self._default_on_accepted
        self.on_rejected  = on_rejected or self._default_on_rejected
        self._pending     = {}
        logger.info(f"[{self.node_id}] LocalMatchNode @ {host}:{port}")

    # ---------- Server ----------

    async def start(self):
        import websockets
        logger.info(f"[{self.node_id}] WS Server ws://{self.host}:{self.port}")
        async with websockets.serve(self._handle_ws, self.host, self.port):
            await asyncio.Future()

    def start_in_thread(self):
        import threading
        def _run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.start())
        t = threading.Thread(target=_run, daemon=True, name=f"A2A-{self.node_id}")
        t.start()
        logger.info(f"[{self.node_id}] WS Server 后台线程已启动")
        return t

    async def _handle_ws(self, websocket):
        peer = websocket.remote_address
        logger.info(f"[{self.node_id}] 连接来自 {peer}")
        try:
            async for raw in websocket:
                try:
                    msg = CLAPMessage.from_json(raw)
                    reply = await self._dispatch(msg)
                    if reply:
                        await websocket.send(reply.to_json())
                except Exception as e:
                    logger.error(f"[{self.node_id}] 处理失败: {e}")
                    err = CLAPMessage(
                        msg_type=MessageType.ERROR, sender_id=self.node_id,
                        receiver_id="unknown",
                        payload={"error": str(e)}, status=StatusCode.SERVER_ERROR)
                    await websocket.send(err.to_json())
        except Exception as e:
            logger.warning(f"[{self.node_id}] 断开 {peer}: {e}")

    async def _dispatch(self, msg):
        if msg.msg_type == MessageType.HANDSHAKE:
            return msg.make_reply(MessageType.HANDSHAKE_ACK,
                {"node_id": self.node_id, "version": "13.0", "ready": True})
        elif msg.msg_type == MessageType.HEARTBEAT:
            return msg.make_reply(MessageType.HEARTBEAT, {"alive": True})
        elif msg.msg_type == MessageType.TRADE_REQUEST:
            return await self._handle_trade_request(msg)
        elif msg.msg_type == MessageType.TRADE_RESPONSE:
            self._handle_trade_response(msg)
        return None

    async def _handle_trade_request(self, msg):
        """核心：收到 TradeRequest -> 本地评分 -> 返回 TradeResponse，数据不出设备"""
        start   = time.time()
        payload = msg.payload
        logger.info(f"[{self.node_id}] TradeRequest from={msg.sender_id} "
                    f"id={payload.get('request_id')}")
        try:
            req = TradeRequest.from_dict(payload)
        except Exception as e:
            return msg.make_reply(MessageType.TRADE_RESPONSE,
                {"status": "error", "error": str(e)}, StatusCode.BAD_REQUEST)

        score, summary = 0.0, "MatchEngine 未配置"
        if self.match_engine:
            try:
                result  = await self.match_engine.match(
                    merchant_id=self.node_id,
                    customer_id=req.customer_id,
                    customer_profile=req.customer_profile,
                )
                score   = result.score
                summary = result.summary
            except Exception as e:
                logger.error(f"[{self.node_id}] MatchEngine 失败: {e}")
        else:
            score, summary = 60.0, "无 MatchEngine，使用默认分"

        status   = "accepted" if score >= req.threshold else "rejected"
        duration = time.time() - start
        resp     = TradeResponse(
            request_id=req.request_id, responder_id=self.node_id,
            status=status, score=score, summary=summary, duration=duration,
        )
        logger.info(f"[{self.node_id}] -> {status} score={score:.1f} dur={duration:.1f}s")
        if resp.accepted:
            self.on_accepted(resp)
        else:
            self.on_rejected(resp)
        return msg.make_reply(
            MessageType.TRADE_RESPONSE, resp.to_dict(),
            StatusCode.ACCEPTED if resp.accepted else StatusCode.REJECTED)

    def _handle_trade_response(self, msg):
        rid = msg.payload.get("request_id", "")
        fut = self._pending.pop(rid, None)
        if fut and not fut.done():
            fut.set_result(msg.payload)

    # ---------- Client ----------

    async def request_trade(self, target_host, target_port,
                            customer_id, customer_profile,
                            menu_context="", max_rounds=5,
                            threshold=75.0, timeout=60.0):
        """向目标节点发起 TradeRequest，等待 TradeResponse"""
        import websockets
        req = TradeRequest(
            requester_id=self.node_id, customer_id=customer_id,
            customer_profile=customer_profile, menu_context=menu_context,
            max_rounds=max_rounds, threshold=threshold,
        )
        msg = CLAPMessage(
            msg_type=MessageType.TRADE_REQUEST,
            sender_id=self.node_id, receiver_id=target_host,
            payload=req.to_dict(),
        )
        uri = f"ws://{target_host}:{target_port}"
        logger.info(f"[{self.node_id}] -> TradeRequest {uri} id={req.request_id}")
        try:
            async with websockets.connect(uri, open_timeout=10) as ws:
                await ws.send(msg.to_json())
                raw  = await asyncio.wait_for(ws.recv(), timeout=timeout)
                resp = CLAPMessage.from_json(raw)
                if resp.msg_type == MessageType.TRADE_RESPONSE:
                    d = resp.payload
                    logger.info(f"[{self.node_id}] Response: {d.get('status')} "
                                f"score={d.get('score',0):.1f}")
                    return d
        except asyncio.TimeoutError:
            logger.error(f"[{self.node_id}] TradeRequest 超时")
        except Exception as e:
            logger.error(f"[{self.node_id}] TradeRequest 失败: {e}")
        return None

    # ---------- 默认回调 ----------

    def _default_on_accepted(self, resp):
        logger.info(f"[{self.node_id}] ✅ 撮合成功 score={resp.score:.1f}% "
                    f"summary={resp.summary[:50]}")

    def _default_on_rejected(self, resp):
        logger.info(f"[{self.node_id}] ❌ 未达标 score={resp.score:.1f}%")


# ==================== 便捷工厂 ====================

def make_handshake(sender_id, receiver_id, meta=None):
    return CLAPMessage(
        msg_type=MessageType.HANDSHAKE, sender_id=sender_id,
        receiver_id=receiver_id,
        payload={"name": sender_id, "version": "13.0", **(meta or {})},
    )


def make_trade_request(sender_id, receiver_id, customer_id,
                       customer_profile, menu_context=""):
    req = TradeRequest(
        requester_id=sender_id, customer_id=customer_id,
        customer_profile=customer_profile, menu_context=menu_context,
    )
    return CLAPMessage(
        msg_type=MessageType.TRADE_REQUEST, sender_id=sender_id,
        receiver_id=receiver_id, payload=req.to_dict(),
    )


# ==================== CLAPAgent（向后兼容 v1.0）====================

class CLAPAgent:
    """兼容 v1.0 asyncio TCP 版本"""

    def __init__(self, agent_id, host="127.0.0.1", port=9000):
        self.agent_id  = agent_id
        self.host      = host
        self.port      = port
        self._handlers = {}
        self._register_defaults()

    def on(self, msg_type):
        def deco(fn):
            self._handlers[msg_type] = fn
            return fn
        return deco

    def _register_defaults(self):
        @self.on(MessageType.HEARTBEAT)
        async def _hb(msg):
            return msg.make_reply(MessageType.HEARTBEAT, {"alive": True})

        @self.on(MessageType.HANDSHAKE)
        async def _hs(msg):
            return msg.make_reply(MessageType.HANDSHAKE_ACK,
                {"agent_id": self.agent_id, "status": "ready"})

    async def _handle_connection(self, reader, writer):
        try:
            while True:
                raw = await reader.readline()
                if not raw:
                    break
                msg     = CLAPMessage.from_json(raw.decode().strip())
                handler = self._handlers.get(msg.msg_type)
                if handler:
                    reply = await handler(msg)
                    if reply:
                        writer.write((reply.to_json() + "\n").encode())
                        await writer.drain()
        except Exception:
            pass
        finally:
            writer.close()

    async def start_server(self):
        srv = await asyncio.start_server(
            self._handle_connection, self.host, self.port)
        async with srv:
            await srv.serve_forever()

    async def send(self, msg, target_host, target_port, timeout=5.0):
        try:
            r, w = await asyncio.wait_for(
                asyncio.open_connection(target_host, target_port), timeout)
            w.write((msg.to_json() + "\n").encode())
            await w.drain()
            raw = await asyncio.wait_for(r.readline(), timeout)
            w.close()
            return CLAPMessage.from_json(raw.decode().strip()) if raw else None
        except Exception as e:
            logger.error(f"CLAPAgent send failed: {e}")
            return None


# ==================== Demo ====================

async def _demo_local_match():
    """本机两节点互相撮合 Demo"""
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    logger.info("=" * 60)
    logger.info("CLAP v2.0 LocalMatchNode Demo")
    logger.info("=" * 60)

    node_b = LocalMatchNode("box-B", host="127.0.0.1", port=9101)
    asyncio.ensure_future(node_b.start())
    await asyncio.sleep(0.5)

    node_a = LocalMatchNode("box-A", host="127.0.0.1", port=9102)
    resp = await node_a.request_trade(
        target_host="127.0.0.1", target_port=9101,
        customer_id="cust-001",
        customer_profile="喜欢麻辣口味，预算30元以内，2人用餐",
        menu_context="招牌：牛肉面18元、麻辣烫15元、套餐A 25元",
    )
    if resp:
        logger.info(f"结果: {resp['status']} score={resp['score']}")
    else:
        logger.error("TradeRequest 失败")


if __name__ == "__main__":
    asyncio.run(_demo_local_match())
