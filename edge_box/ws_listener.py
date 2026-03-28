"""
edge_box/ws_listener.py
Project Claw - B端 Edge Box WebSocket 监听器 v14.3

新增：
- 处理 execute_trade 信令时接入 PaymentVerifier
- 步骤A：生成固定金额收款码并发送
- 步骤B：60s 视觉轮询 → PAYMENT_SUCCESS_ACK / TRADE_TIMEOUT
- 所有状态流转记录在 TransactionLedger
"""
from __future__ import annotations

import asyncio
import json
import logging
import time

import websockets

from agent_workflow import DarkNetNegotiator
from config import settings
from edge_box.base_driver import get_driver
from edge_box.payment_verifier import PaymentVerifier, VerifyResult
from edge_box.physical_tool import notify_and_send_qrcode
from logger_setup import setup_logger
from shared.claw_protocol import A2A_DialogueTurn, A2A_TradeDecision, Decision

logger = setup_logger("claw.edge.ws_listener")


class EdgeBoxWSListener:
    """分离 A2A 机器谈判与 UI 物理执行的边缘监听器。"""

    def __init__(self, merchant_id: str | None = None):
        self.merchant_id  = merchant_id or settings.A2A_MERCHANT_ID
        self.negotiator   = DarkNetNegotiator()
        self._driver      = get_driver()
        self._verifier    = PaymentVerifier(driver=self._driver)
        self._trade_ws    = None   # 保存当前 WS 连接，供 ACK 回调使用
        self._stop        = False

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

    # ── 重连循环 ────────────────────────────────────────────────────────────
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

    # ── Trade 通道 ──────────────────────────────────────────────────────────
    async def _run_trade_channel(self) -> None:
        logger.info(f"[WSListener] connect trade channel: {self.merchant_ws_url}")
        async with websockets.connect(
            self.merchant_ws_url, ping_interval=20, ping_timeout=10
        ) as ws:
            self._trade_ws = ws
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
                elif msg_type == "execute_trade":
                    await self._handle_execute_trade(ws, msg)
                elif msg_type == "a2a_trade_decision":
                    await self._handle_decision(msg)
                elif msg_type == "ping":
                    await ws.send(json.dumps({"type": "pong", "ts": time.time()}))

    # ── Dialogue 通道 ───────────────────────────────────────────────────────
    async def _run_dialogue_channel(self) -> None:
        logger.info(f"[WSListener] connect dialogue channel: {self.dialogue_ws_url}")
        async with websockets.connect(
            self.dialogue_ws_url, ping_interval=20, ping_timeout=10
        ) as ws:
            while not self._stop:
                raw = await ws.recv()
                try:
                    msg = json.loads(raw)
                except Exception:
                    logger.warning("[WSListener] dialogue non-json message dropped")
                    continue
                if msg.get("type") == "a2a_dialogue_turn":
                    await self._handle_dialogue_turn(ws, msg)

    # ── 处理谈判意图 ────────────────────────────────────────────────────────
    async def _handle_intent(self, ws, msg: dict) -> None:
        try:
            intent = self._parse_intent(msg.get("intent", {}))
            offer  = await self.negotiator.negotiate_intent(
                intent=intent, merchant_id=self.merchant_id,
            )
            await ws.send(json.dumps({
                "type": "a2a_merchant_offer",
                "offer": offer.model_dump(mode="json"),
                "ts": time.time(),
            }, ensure_ascii=False))
        except Exception as e:
            logger.error(f"[WSListener] intent process failed: {e}")

    # ── 处理成交信令（核心改造）─────────────────────────────────────────────
    async def _handle_execute_trade(self, ws, msg: dict) -> None:
        """
        收到 execute_trade 信令：
        1. 调用 PaymentVerifier 步骤A（生成收款码）
        2. 启动步骤B（60s 视觉轮询）
        3. 捕获成功 → 发 PAYMENT_SUCCESS_ACK
           超时    → 发 TRADE_TIMEOUT
        """
        intent_id   = msg.get("intent_id", "")
        client_id   = msg.get("client_id", "")
        merchant_id = msg.get("merchant_id", self.merchant_id)
        final_price = float(msg.get("final_price", 0))
        reply_text  = msg.get("reply_text", "接单成功")

        logger.info(
            f"[WSListener] execute_trade 收到 intent={intent_id} "
            f"price=¥{final_price} client={client_id}"
        )

        # 回调：支付成功 → 发 PAYMENT_SUCCESS_ACK
        def on_success(result: VerifyResult) -> None:
            asyncio.ensure_future(
                self._send_payment_ack(
                    ws          = ws,
                    intent_id   = intent_id,
                    trade_id    = result.trade_id,
                    proof_hash  = result.visual_proof_hash,
                    ocr_snippet = result.ocr_snippet,
                    elapsed_sec = result.elapsed_sec,
                )
            )

        # 回调：超时 → 发 TRADE_TIMEOUT 熔断
        def on_timeout(result: VerifyResult) -> None:
            asyncio.ensure_future(
                self._send_trade_timeout(
                    ws        = ws,
                    intent_id = intent_id,
                    trade_id  = result.trade_id,
                    reason    = result.reason,
                )
            )

        try:
            trade_id = await self._verifier.handle_execute_trade(
                intent_id   = intent_id,
                client_id   = client_id,
                merchant_id = merchant_id,
                final_price = final_price,
                reply_text  = reply_text,
                on_success  = on_success,
                on_timeout  = on_timeout,
            )
            logger.info(f"[WSListener] PaymentVerifier 已启动 trade={trade_id}")
        except Exception as e:
            logger.error(f"[WSListener] execute_trade 处理失败: {e}")
            await self._send_trade_timeout(ws, intent_id, "ERROR", str(e))

    # ── 发送 PAYMENT_SUCCESS_ACK ────────────────────────────────────────────
    async def _send_payment_ack(
        self,
        ws:          websockets.WebSocketClientProtocol,
        intent_id:   str,
        trade_id:    str,
        proof_hash:  str | None,
        ocr_snippet: str | None,
        elapsed_sec: float,
    ) -> None:
        payload = {
            "type":              "PAYMENT_SUCCESS_ACK",
            "intent_id":         intent_id,
            "trade_id":          trade_id,
            "merchant_id":       self.merchant_id,
            "visual_proof_hash": proof_hash,
            "ocr_snippet":       ocr_snippet,
            "elapsed_sec":       round(elapsed_sec, 2),
            "ts":                time.time(),
        }
        try:
            await ws.send(json.dumps(payload, ensure_ascii=False))
            logger.info(
                f"[WSListener] PAYMENT_SUCCESS_ACK sent "
                f"trade={trade_id} proof={proof_hash and proof_hash[:12]}..."
            )
        except Exception as e:
            logger.error(f"[WSListener] 发送 PAYMENT_SUCCESS_ACK 失败: {e}")

    # ── 发送 TRADE_TIMEOUT（熔断回滚）──────────────────────────────────────
    async def _send_trade_timeout(
        self,
        ws:        websockets.WebSocketClientProtocol,
        intent_id: str,
        trade_id:  str,
        reason:    str,
    ) -> None:
        payload = {
            "type":        "TRADE_TIMEOUT",
            "intent_id":   intent_id,
            "trade_id":    trade_id,
            "merchant_id": self.merchant_id,
            "reason":      reason,
            "ts":          time.time(),
        }
        try:
            await ws.send(json.dumps(payload, ensure_ascii=False))
            logger.warning(
                f"[WSListener] TRADE_TIMEOUT sent trade={trade_id} reason={reason}"
            )
        except Exception as e:
            logger.error(f"[WSListener] 发送 TRADE_TIMEOUT 失败: {e}")

    # ── 处理对话轮 ──────────────────────────────────────────────────────────
    async def _handle_dialogue_turn(self, ws, msg: dict) -> None:
        try:
            turn = A2A_DialogueTurn.model_validate(msg.get("turn", {}))
            if turn.receiver_id != self.merchant_id:
                return
            generated = await self.negotiator.negotiate_dialogue_turn(
                session_id    = turn.session_id,
                intent_id     = turn.intent_id,
                merchant_id   = self.merchant_id,
                item_name     = "未知商品",
                client_text   = turn.text,
                expected_price= turn.expected_price,
                round_no      = turn.round,
                strategy_hint = turn.strategy_hint,
            )
            generated["receiver_id"] = turn.sender_id
            await ws.send(json.dumps(
                {"type": "a2a_dialogue_turn", "turn": generated, "ts": time.time()},
                ensure_ascii=False,
            ))
        except Exception as e:
            logger.error(f"[WSListener] dialogue turn failed: {e}")

    # ── 旧版 decision 兼容处理 ──────────────────────────────────────────────
    async def _handle_decision(self, msg: dict) -> None:
        try:
            decision = A2A_TradeDecision.model_validate(msg.get("decision", {}))
            if decision.decision == Decision.ACCEPT:
                price = float(msg.get("final_price", 0) or 0)
                await asyncio.to_thread(
                    notify_and_send_qrcode, price, None, self._driver
                )
        except Exception as e:
            logger.error(f"[WSListener] decision handle failed: {e}")

    @staticmethod
    def _parse_intent(data: dict):
        from shared.claw_protocol import A2A_TradeIntent
        return A2A_TradeIntent.model_validate(data)


if __name__ == "__main__":
    listener = EdgeBoxWSListener()
    asyncio.run(listener.run_forever())
