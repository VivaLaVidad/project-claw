"""
Project Claw v13.1 - a2a_box_client.py
B 端龙虾盒子 WebSocket 客户端（协议优先）

职责：
  1. 连接信令服务器，注册 B 端节点
  2. 接收 ClientIntent -> 调用 BusinessBrain 本地评分 -> 回传 MerchantOffer
  3. 接收 ExecuteTrade -> 仅执行 UI 动作（不参与主业务决策）
  4. 支持 secure_envelope（HMAC 签名 + 可选加密）
  5. 断线自动重连（指数退避），心跳 Pong 保活
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
from typing import Callable, Optional

from config import settings
from logger_setup import setup_logger
from secure_comm import SecureEnvelopeError, build_secure_envelope, verify_and_unpack_envelope

logger = setup_logger("claw.box_client")

RECONNECT_DELAYS = [2, 4, 8, 16, 30, 60]


def build_box_server_url(merchant_id: str) -> str:
    return settings.signaling_merchant_ws_url(merchant_id)


class A2ABoxClient:
    def __init__(
        self,
        merchant_id: str,
        server_url: str,
        brain_workflow,
        on_execute_trade: Optional[Callable] = None,
        reconnect_delays: list | None = None,
        signing_secret: str = "",
        encryption_key: str = "",
    ):
        self.merchant_id = merchant_id
        self.server_url = server_url
        self.brain_workflow = brain_workflow
        self.on_execute_trade = on_execute_trade or self._default_execute_trade
        self.reconnect_delays = reconnect_delays or RECONNECT_DELAYS
        self.signing_secret = signing_secret or settings.A2A_SIGNING_SECRET
        self.encryption_key = encryption_key or settings.A2A_ENCRYPTION_KEY
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = False

    def start(self) -> threading.Thread:
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name=f"A2ABoxClient-{self.merchant_id}")
        self._thread.start()
        logger.info(f"[BoxClient:{self.merchant_id}] 后台线程启动")
        return self._thread

    def stop(self):
        self._stop = True

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._connect_with_retry())

    async def _connect_with_retry(self):
        attempt = 0
        while not self._stop:
            try:
                await self._run_session()
            except Exception as e:
                if self._stop:
                    break
                delay = self.reconnect_delays[min(attempt, len(self.reconnect_delays) - 1)]
                logger.warning(f"[BoxClient:{self.merchant_id}] 连接断开: {e}，{delay}s 后重连 (attempt {attempt + 1})")
                await asyncio.sleep(delay)
                attempt += 1
            else:
                attempt = 0

    async def _run_session(self):
        import websockets

        logger.info(f"[BoxClient:{self.merchant_id}] 连接 {self.server_url}")
        async with websockets.connect(self.server_url, open_timeout=10, ping_interval=20, ping_timeout=10) as ws:
            logger.info(f"[BoxClient:{self.merchant_id}] ✅ 已连接信令服务器")
            logger.a2a_handshake(f"register:{self.merchant_id}@{self.server_url}")

            register_payload = {
                "type": "register",
                "merchant_id": self.merchant_id,
                "version": "13.1",
                "merchant_tags": [x.strip() for x in settings.A2A_MERCHANT_TAGS.split(",") if x.strip()],
                "ts": time.time(),
            }
            register_env = build_secure_envelope(
                payload=register_payload,
                sender_id=self.merchant_id,
                receiver_id="signaling",
                secret=self.signing_secret,
                encryption_key=self.encryption_key,
            )
            await ws.send(json.dumps({"type": "secure_envelope", "envelope": register_env}, ensure_ascii=False))

            async for raw in ws:
                if self._stop:
                    break
                try:
                    data = json.loads(raw)
                    await self._dispatch(ws, data)
                except json.JSONDecodeError:
                    logger.warning(f"[BoxClient] 非 JSON 消息: {raw[:80]}")
                except Exception as e:
                    logger.error(f"[BoxClient] 处理消息异常: {e}")

    async def _dispatch(self, ws, data: dict):
        msg_type = data.get("type", "")

        if msg_type == "ping":
            await ws.send(json.dumps({"type": "pong", "ts": time.time()}))
            return

        if msg_type == "secure_envelope":
            env = data.get("envelope", {})
            try:
                payload = verify_and_unpack_envelope(
                    envelope=env,
                    expected_receiver_id=self.merchant_id,
                    secret=self.signing_secret,
                    encryption_key=self.encryption_key,
                )
                await self._dispatch(ws, payload)
            except SecureEnvelopeError as e:
                logger.warning(f"[BoxClient:{self.merchant_id}] 丢弃非法安全消息: {e}")
            return

        if msg_type == "registered":
            logger.info(f"[BoxClient:{self.merchant_id}] 注册确认: {data}")
            return

        if msg_type == "intent_broadcast":
            await self._handle_intent(ws, data)
            return

        if msg_type == "execute_trade":
            await self._handle_execute_trade(data)
            return

        logger.debug(f"[BoxClient] 未知消息类型: {msg_type}")

    async def _handle_intent(self, ws, data: dict):
        intent_id = data.get("intent_id", "")
        demand_text = data.get("demand_text", "")
        max_price = float(data.get("max_price", 9999))
        client_id = data.get("client_id", "unknown")

        logger.info(
            f"[BoxClient:{self.merchant_id}] 收到 Intent id={intent_id} demand={demand_text[:30]} max_price={max_price}"
        )
        logger.a2a_handshake(f"intent:{client_id}->{self.merchant_id}:{intent_id}")

        offer = await asyncio.to_thread(self._run_brain_a2a, demand_text, max_price)
        if not offer or not offer.get("viable"):
            logger.info(f"[BoxClient:{self.merchant_id}] 报价不可行，跳过")
            return

        offer_payload = {
            "type": "offer",
            "intent_id": intent_id,
            "merchant_id": self.merchant_id,
            "reply_text": offer.get("reply_text", ""),
            "final_price": offer.get("final_price", 0),
            "match_score": offer.get("match_score", 0),
            "eta_minutes": int(offer.get("eta_minutes", 0) or 0),
            "offer_tags": list(offer.get("offer_tags", []) or []),
            "ts": time.time(),
        }
        offer_env = build_secure_envelope(
            payload=offer_payload,
            sender_id=self.merchant_id,
            receiver_id="signaling",
            secret=self.signing_secret,
            encryption_key=self.encryption_key,
        )
        await ws.send(json.dumps({"type": "secure_envelope", "envelope": offer_env}, ensure_ascii=False))
        logger.info(
            f"[BoxClient:{self.merchant_id}] ✅ MerchantOffer 已回传 price={offer.get('final_price')} score={offer.get('match_score'):.1f}"
        )

    def _run_brain_a2a(self, demand_text: str, max_price: float) -> dict:
        from business_brain import BrainState

        try:
            state = BrainState(user_message=demand_text, user_id="a2a_system", extra={"is_a2a": True, "max_price": max_price})
            result = self.brain_workflow.invoke(state)
            return result.get("a2a_offer", {})
        except Exception as e:
            logger.error(f"[BoxClient] BusinessBrain 调用失败: {e}")
            return {"viable": False, "error": str(e)}

    async def _handle_execute_trade(self, data: dict):
        logger.info(f"[BoxClient:{self.merchant_id}] ⚡ ExecuteTrade 收到！ client_id={data.get('client_id')} price={data.get('final_price')}")
        await asyncio.to_thread(self._do_execute_trade, data)

    def _do_execute_trade(self, trade: dict):
        try:
            self.on_execute_trade(trade)
        except Exception as e:
            logger.error(f"[BoxClient] ExecuteTrade 执行失败: {e}")

    def _default_execute_trade(self, trade: dict):
        logger.info(
            f"[BoxClient] [DEFAULT] ExecuteTrade:\n"
            f"  client_id   = {trade.get('client_id')}\n"
            f"  final_price = {trade.get('final_price')}\n"
            f"  reply_text  = {trade.get('reply_text')}\n"
            f"  需要 uiautomator2 发消息 + 收款码"
        )


def make_execute_trade_handler(verifier, payment_sender, input_x: float, input_y: float):
    def handler(trade: dict):
        final_price = float(trade.get("final_price", 0))
        reply_text = trade.get("reply_text", "")
        greet = f"兄弟你好！你在小程序上选择了我们的报价，{reply_text}，总计{final_price:.0f}元！"
        ok = verifier.send_with_verify(input_x, input_y, greet)
        logger.info(f"[ExecuteTrade] 确认消息发送: {'✅' if ok else '❌'}")
        time.sleep(0.5)
        if final_price > 0:
            payment_sender.send_payment_code(final_price)

    return handler
