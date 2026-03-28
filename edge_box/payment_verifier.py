"""
edge_box/payment_verifier.py
Project Claw v14.3 - PaymentVerifier 核心模块

功能：
步骤 A - 生成固定金额收款码并发送给客户
步骤 B - 60s 异步视觉轮询：监控通知栏/微信前台
         EasyOCR/YOLO 识别 ['微信支付','收款','¥{price}'] 关键词
         捕获 → PAYMENT_SUCCESS_ACK
         超时 → TRADE_TIMEOUT 熔断回滚

所有状态流转记录在 TransactionLedger（防篡改 SQLite）中。
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
import uuid
from dataclasses import dataclass
from typing import Callable, List, Optional

from edge_box.base_driver import BaseDriver
from edge_box.transaction_ledger import TradeStatus, TransactionLedger, transaction_ledger

logger = logging.getLogger("claw.edge.payment_verifier")

# ─── 配置 ────────────────────────────────────────────────────────────────────
VISUAL_POLL_INTERVAL_SEC = 2.0    # 每次截图间隔
VISUAL_ACK_TIMEOUT_SEC   = 60.0   # 最长等待时间
OCR_CONFIDENCE_THRESHOLD = 0.55   # EasyOCR 置信度阈值

# 微信支付通知关键词
PAYMENT_KEYWORDS = ["微信支付", "收款", "转账", "已收款", "付款成功"]


# ─── 结果数据类 ───────────────────────────────────────────────────────────────
@dataclass
class VerifyResult:
    success:           bool
    trade_id:          str
    visual_proof_hash: Optional[str] = None
    ocr_snippet:       Optional[str] = None
    elapsed_sec:       float         = 0.0
    reason:            str           = ""


# ─── OCR 引擎封装 ─────────────────────────────────────────────────────────────
class _OCREngine:
    """
    懒加载 EasyOCR。
    Railway 云端无 easyocr 时自动降级为空结果。
    """
    _reader = None
    _available: Optional[bool] = None

    @classmethod
    def available(cls) -> bool:
        if cls._available is None:
            try:
                import easyocr  # noqa: F401
                cls._available = True
            except ImportError:
                cls._available = False
                logger.warning("[OCR] easyocr 未安装，视觉验证将使用降级策略")
        return cls._available

    @classmethod
    def read(cls, image_bytes: bytes) -> List[str]:
        """返回识别到的文本列表（过滤低置信度结果）"""
        if not cls.available():
            return []
        try:
            import easyocr
            import numpy as np
            from PIL import Image
            import io
            if cls._reader is None:
                cls._reader = easyocr.Reader(["ch_sim", "en"], gpu=False, verbose=False)
            img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            arr = np.array(img)
            results = cls._reader.readtext(arr, detail=1)
            return [
                text for (_, text, conf) in results
                if conf >= OCR_CONFIDENCE_THRESHOLD
            ]
        except Exception as e:
            logger.error(f"[OCR] readtext failed: {e}")
            return []


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _match_payment_keywords(texts: List[str], price: float) -> Optional[str]:
    """
    检查 OCR 结果是否包含支付通知关键词 + 金额匹配。
    返回匹配到的片段，否则 None。
    """
    combined = " ".join(texts)
    # 检查通用支付关键词
    has_keyword = any(kw in combined for kw in PAYMENT_KEYWORDS)
    if not has_keyword:
        return None
    # 检查金额匹配（允许 ¥18、¥18.5、18.50 等格式）
    price_patterns = [
        rf"[¥￥]\s*{re.escape(str(int(price)))}",
        rf"[¥￥]\s*{re.escape(f'{price:.1f}')}",
        rf"[¥￥]\s*{re.escape(f'{price:.2f}')}",
        rf"{re.escape(str(int(price)))}\s*元",
    ]
    for pat in price_patterns:
        if re.search(pat, combined):
            snippet = combined[:120]
            return snippet
    # 关键词存在但金额不匹配 → 不触发
    return None


# ─── PaymentVerifier ─────────────────────────────────────────────────────────
class PaymentVerifier:
    """
    支付验证器。

    步骤 A：调用 BaseDriver 生成固定金额收款码，发送消息给客户。
    步骤 B：异步轮询 60s，截图 + OCR，监听微信支付通知。
             捕获 → PAYMENT_SUCCESS_ACK callback
             超时 → TRADE_TIMEOUT callback

    所有状态写入 TransactionLedger。
    """

    def __init__(
        self,
        driver:  BaseDriver,
        ledger:  TransactionLedger = transaction_ledger,
    ) -> None:
        self._driver = driver
        self._ledger = ledger

    async def handle_execute_trade(
        self,
        intent_id:   str,
        client_id:   str,
        merchant_id: str,
        final_price: float,
        reply_text:  str,
        on_success:  Callable[[VerifyResult], None],
        on_timeout:  Callable[[VerifyResult], None],
    ) -> str:
        """
        主入口：处理 ExecuteTrade 信令。

        Args:
            intent_id:   A2A 意图 ID
            client_id:   消费者 ID
            merchant_id: 商家 ID
            final_price: 成交金额（元）
            reply_text:  发给客户的确认消息
            on_success:  视觉捕获到支付后的回调
            on_timeout:  超时熔断回滚回调

        Returns:
            trade_id（本次交易唯一 ID）
        """
        trade_id = f"TRD-{uuid.uuid4().hex[:12].upper()}"
        logger.info(
            f"[PaymentVerifier] 开始处理 trade={trade_id} "
            f"intent={intent_id} price=¥{final_price}"
        )

        # 记录账本：INITIATED
        self._ledger.initiate(
            trade_id    = trade_id,
            intent_id   = intent_id,
            client_id   = client_id,
            merchant_id = merchant_id,
            amount_yuan = final_price,
        )

        # 步骤 A：生成收款码并发送
        await asyncio.to_thread(
            self._step_a_generate_and_send,
            trade_id, final_price, reply_text,
        )

        # 步骤 B：异步视觉轮询（不阻塞当前 WS 连接）
        asyncio.ensure_future(
            self._step_b_visual_poll(
                trade_id    = trade_id,
                final_price = final_price,
                on_success  = on_success,
                on_timeout  = on_timeout,
            )
        )

        return trade_id

    # ── 步骤 A ──────────────────────────────────────────────────────────────
    def _step_a_generate_and_send(
        self,
        trade_id:    str,
        final_price: float,
        reply_text:  str,
    ) -> None:
        """
        调用 BaseDriver 生成固定金额收款码，
        通过微信发送给客户。
        """
        try:
            # 1. 打开微信收款界面（固定金额）
            ok = self._driver.open_wechat_receive_money(final_price)
            if not ok:
                logger.warning("[PaymentVerifier] open_wechat_receive_money 失败，降级发文本")

            # 2. 生成收款码截图/链接
            qr_path = self._driver.generate_payment_qr(
                amount_yuan = final_price,
                description = f"Project Claw 订单 {trade_id[:8]}",
            )
            logger.info(f"[PaymentVerifier] 收款码已生成: {qr_path}")

            # 3. 发送确认消息给客户
            msg = (
                f"{reply_text}\n"
                f"收款金额：¥{final_price:.1f}\n"
                f"请扫码或点击链接完成支付（订单：{trade_id[:8]}）"
            )
            self._driver.send_wechat_message(msg)

            # 4. 记录账本：QR_GENERATED
            self._ledger.update(
                trade_id = trade_id,
                status   = TradeStatus.QR_GENERATED,
                extra    = {"qr_path": qr_path, "msg": msg},
            )
            logger.info(f"[PaymentVerifier] 步骤A完成 trade={trade_id}")

        except Exception as e:
            logger.error(f"[PaymentVerifier] 步骤A失败: {e}")
            self._ledger.update(
                trade_id = trade_id,
                status   = TradeStatus.FAILED,
                extra    = {"error": str(e), "step": "A"},
            )

    # ── 步骤 B ──────────────────────────────────────────────────────────────
    async def _step_b_visual_poll(
        self,
        trade_id:    str,
        final_price: float,
        on_success:  Callable[[VerifyResult], None],
        on_timeout:  Callable[[VerifyResult], None],
    ) -> None:
        """
        限时 60s 异步视觉轮询：
        截图 → OCR → 关键词匹配 → 触发 ACK 或超时熔断
        """
        self._ledger.update(trade_id=trade_id, status=TradeStatus.POLLING)
        start_time  = time.time()
        poll_count  = 0

        logger.info(
            f"[PaymentVerifier] 步骤B开始视觉轮询 trade={trade_id} "
            f"timeout={VISUAL_ACK_TIMEOUT_SEC}s"
        )

        while True:
            elapsed = time.time() - start_time

            # ── 超时熔断 ──
            if elapsed >= VISUAL_ACK_TIMEOUT_SEC:
                logger.warning(
                    f"[PaymentVerifier] 视觉轮询超时 trade={trade_id} "
                    f"elapsed={elapsed:.1f}s polls={poll_count}"
                )
                self._ledger.update(
                    trade_id = trade_id,
                    status   = TradeStatus.TIMEOUT,
                    extra    = {"elapsed": elapsed, "polls": poll_count},
                )
                result = VerifyResult(
                    success     = False,
                    trade_id    = trade_id,
                    elapsed_sec = elapsed,
                    reason      = f"视觉轮询超时（{VISUAL_ACK_TIMEOUT_SEC}s）",
                )
                try:
                    on_timeout(result)
                except Exception as e:
                    logger.error(f"[PaymentVerifier] on_timeout callback error: {e}")
                return

            # ── 截图 ──
            try:
                # 拉下通知栏，增加捕获概率
                await asyncio.to_thread(self._driver.swipe_down_notification)
                await asyncio.sleep(0.3)

                screenshot_bytes = await asyncio.to_thread(self._driver.get_screenshot)
                proof_hash       = _sha256_bytes(screenshot_bytes)
                poll_count      += 1

                logger.debug(
                    f"[PaymentVerifier] poll #{poll_count} "
                    f"hash={proof_hash[:12]}... elapsed={elapsed:.1f}s"
                )
            except Exception as e:
                logger.error(f"[PaymentVerifier] 截图失败: {e}")
                await asyncio.sleep(VISUAL_POLL_INTERVAL_SEC)
                continue

            # ── OCR 识别 ──
            texts   = await asyncio.to_thread(_OCREngine.read, screenshot_bytes)
            snippet = _match_payment_keywords(texts, final_price)

            if snippet:
                # ── 捕获到支付通知 ──
                logger.info(
                    f"[PaymentVerifier] 支付通知捕获! trade={trade_id} "
                    f"snippet={snippet!r} hash={proof_hash[:12]}..."
                )
                self._ledger.update(
                    trade_id          = trade_id,
                    status            = TradeStatus.PAYMENT_DETECTED,
                    visual_proof_hash = proof_hash,
                    ocr_snippet       = snippet,
                )
                self._ledger.update(
                    trade_id          = trade_id,
                    status            = TradeStatus.ACK_SENT,
                    visual_proof_hash = proof_hash,
                    ocr_snippet       = snippet,
                )
                result = VerifyResult(
                    success           = True,
                    trade_id          = trade_id,
                    visual_proof_hash = proof_hash,
                    ocr_snippet       = snippet,
                    elapsed_sec       = elapsed,
                    reason            = "视觉捕获微信支付通知",
                )
                try:
                    on_success(result)
                except Exception as e:
                    logger.error(f"[PaymentVerifier] on_success callback error: {e}")
                return

            # ── 未捕获，等待下次轮询 ──
            await asyncio.sleep(VISUAL_POLL_INTERVAL_SEC)
