from __future__ import annotations

import asyncio
import json
import time

import websockets

from agent_workflow import DarkNetNegotiator
from config import settings
from edge_box.physical_tool import notify_and_send_qrcode
from logger_setup import setup_logger
from shared.claw_protocol import A2A_DialogueTurn, A2A_TradeDecision, Decision


logger = setup_logger("claw.edge.ws_listener")


class EdgeBoxWSListener:
    """分离 A2A 机器谈判与 UI 物理执行的边缘监听器。"""

    def __init__(self, merchant_id: str | None = None):
        self.merchant_id = merchant_id or settings.A2A_MERCHANT_ID
        self.negotiator = DarkNetNegotiator()
        self._stop = False

    @property
    def merchant_ws_url(self) -> str:
        return f"{settings.signaling_ws_base_url}/ws/a2a/merchant/{self.merchant_id}"

    @property
    def dialogue_ws_url(self) -> str:
        return f"{settings.signaling_ws_base_url}/ws/a2a/dialogue/merchant/{self.merchant_id}"

    async def run_forever(self) -> None:
        await asyncio.gather(
            self._run_trade_channel_forever(),
            self._run_dialogue_channel_forever(),
        )

    def stop(self) -> None:
        self._stop = True

    async def _run_trade_channel_forever(self) -> None:
        retry = 2
        while not self._stop:
            try:
                await self._run_trade_channel()
                retry = 2
            except Exception as e:
                logger.error(f"[WSListener] trade channel error: {e}; retry in {retry}s")
                await asyncio.sleep(retry)
                retry = min(30, retry * 2)

    async def _run_dialogue_channel_forever(self) -> None:
        retry = 2
        while not self._stop:
            try:
                await self._run_dialogue_channel()
                retry = 2
            except Exception as e:
                logger.error(f"[WSListener] dialogue channel error: {e}; retry in {retry}s")
                await asyncio.sleep(retry)
                retry = min(30, retry * 2)

    async def _run_trade_channel(self) -> None:
        logger.info(f"[WSListener] connect trade channel: {self.merchant_ws_url}")
        async with websockets.connect(self.merchant_ws_url, ping_interval=20, ping_timeout=10) as ws:
            while not self._stop:
                raw = await ws.recv()
                try:
                    msg = json.loads(raw)
                except Exception:
                    logger.warning("[WSListener] non-json message dropped")
                    continue

                msg_type = msg.get("type", "")
                if msg_type == "a2a_trade_intent":
                    await self._handle_intent(ws, msg)
                elif msg_type == "a2a_trade_decision":
                    await self._handle_decision(msg)

    async def _run_dialogue_channel(self) -> None:
        logger.info(f"[WSListener] connect dialogue channel: {self.dialogue_ws_url}")
        async with websockets.connect(self.dialogue_ws_url, ping_interval=20, ping_timeout=10) as ws:
            while not self._stop:
                raw = await ws.recv()
                try:
                    msg = json.loads(raw)
                except Exception:
                    logger.warning("[WSListener] dialogue non-json message dropped")
                    continue
                if msg.get("type") == "a2a_dialogue_turn":
                    await self._handle_dialogue_turn(ws, msg)

    async def _handle_intent(self, ws, msg: dict) -> None:
        try:
            intent = self._parse_intent(msg.get("intent", {}))
            offer = await self.negotiator.negotiate_intent(
                intent=intent,
                merchant_id=self.merchant_id,
            )
            payload = {
                "type": "a2a_merchant_offer",
                "offer": offer.model_dump(mode="json"),
                "ts": time.time(),
            }
            await ws.send(json.dumps(payload, ensure_ascii=False))
        except Exception as e:
            logger.error(f"[WSListener] intent process failed: {e}")

    async def _handle_dialogue_turn(self, ws, msg: dict) -> None:
        try:
            turn = A2A_DialogueTurn.model_validate(msg.get("turn", {}))
            if turn.receiver_id != self.merchant_id:
                return
            generated = await self.negotiator.negotiate_dialogue_turn(
                session_id=turn.session_id,
                intent_id=turn.intent_id,
                merchant_id=self.merchant_id,
                item_name="未知商品",
                client_text=turn.text,
                expected_price=turn.expected_price,
                round_no=turn.round,
                strategy_hint=turn.strategy_hint,
            )
            generated["receiver_id"] = turn.sender_id
            payload = {"type": "a2a_dialogue_turn", "turn": generated, "ts": time.time()}
            await ws.send(json.dumps(payload, ensure_ascii=False))
        except Exception as e:
            logger.error(f"[WSListener] dialogue turn failed: {e}")

    async def _handle_decision(self, msg: dict) -> None:
        try:
            decision = A2A_TradeDecision.model_validate(msg.get("decision", {}))
            if decision.decision == Decision.ACCEPT:
                price = float(msg.get("final_price", 0) or 0)
                await asyncio.to_thread(notify_and_send_qrcode, price)
        except Exception as e:
            logger.error(f"[WSListener] decision handle failed: {e}")

    @staticmethod
    def _parse_intent(data: dict):
        from shared.claw_protocol import A2A_TradeIntent

        return A2A_TradeIntent.model_validate(data)


if __name__ == "__main__":
    listener = EdgeBoxWSListener()
    asyncio.run(listener.run_forever())
