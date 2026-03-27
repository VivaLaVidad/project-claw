from __future__ import annotations

import time
from typing import Optional

from config import settings
from edge_driver import BaseDriver
from logger_setup import setup_logger


class UIVerifier:
    def __init__(self, device: BaseDriver, timeout: float = 2.0, max_retries: int = 2):
        self.d = device
        self.timeout = timeout
        self.max_retries = max_retries
        self._log = setup_logger("claw.ui")

    def set_driver(self, device: BaseDriver) -> None:
        self.d = device

    def verify_sent(self, input_x: float, input_y: float) -> bool:
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            try:
                el = self.d.xpath('//android.widget.EditText')
                if el.exists:
                    if not (el.get_text() or "").strip():
                        return True
            except Exception:
                pass
            time.sleep(0.1)
        return False

    def send_with_verify(self, input_x: float, input_y: float, reply: str) -> bool:
        try:
            self.d.click(input_x, input_y)
            self._log.execute_rpa(input_x, input_y)
            time.sleep(settings.INPUT_DELAY_BEFORE)
            self.d.send_keys(reply)
            time.sleep(settings.INPUT_DELAY_AFTER)
            self.d.press("enter")
            self._log.info("🚀 消息已发送")
        except Exception as e:
            self._log.error(f"❌ 发送异常: {e}")
            return False
        if not settings.UI_VERIFY_ENABLED:
            return True
        if self.verify_sent(input_x, input_y):
            self._log.info("✅ 发送校验通过")
            return True
        self._log.warning("⚠️ 校验超时，但消息已按 Enter，视为成功")
        return True


class PaymentSender:
    DEFAULT_QR_PATH = "./payment_qr.png"

    def __init__(self, device: BaseDriver, input_x: float, input_y: float, qr_path: str = DEFAULT_QR_PATH):
        self.d = device
        self.input_x = input_x
        self.input_y = input_y
        self.qr_path = qr_path
        self._log = setup_logger("claw.payment")

    def set_driver(self, device: BaseDriver) -> None:
        self.d = device

    def set_input_position(self, input_x: float, input_y: float) -> None:
        self.input_x = input_x
        self.input_y = input_y

    def send_payment_code(self, price: float) -> bool:
        self._log.info(f"[PaymentSender] 触发收款，金额={price}元")
        if self._try_send_image(price):
            return True
        return self._try_send_text(price)

    def _try_send_image(self, price: float) -> bool:
        import os

        if not os.path.exists(self.qr_path):
            self._log.warning(
                f"[PaymentSender] 收款码图片不存在: {self.qr_path}，请将商家收款码截图保存至该路径"
            )
            return False
        try:
            remote = "/sdcard/Pictures/payment_qr.png"
            self.d.push(self.qr_path, remote)
            self._log.info(f"[PaymentSender] 图片已推送: {remote}")
            time.sleep(0.5)

            more = self.d.xpath(
                '//android.widget.ImageView[@content-desc="更多"]'
                ' | //*[@resource-id="com.tencent.mm:id/bfp"]'
            )
            if more.exists:
                more.click()
                self._log.execute_rpa(self.input_x + 130, self.input_y)
                self._log.info("[PaymentSender] 点击 + 更多")
            else:
                self.d.click(self.input_x + 130, self.input_y)
                self._log.execute_rpa(self.input_x + 130, self.input_y)
                self._log.warning("[PaymentSender] + xpath 未找到，使用坐标偏移")
            time.sleep(0.8)

            album = self.d.xpath('//*[@content-desc="相册"] | //*[@content-desc="Photo Library"]')
            if album.exists:
                album.click()
                self._log.execute_rpa(self.input_x + 60, self.input_y - 220)
                self._log.info("[PaymentSender] 点击相册")
                time.sleep(1.2)
            else:
                self._log.warning("[PaymentSender] 相册未找到，退出")
                self.d.press("back")
                return False

            thumb = self.d.xpath(
                '//*[@resource-id="com.tencent.mm:id/h1y"]'
                ' | //*[@resource-id="com.tencent.mm:id/thumbnail"]'
            )
            if thumb.exists:
                thumb.click()
                self._log.execute_rpa(self.input_x - 120, self.input_y - 420)
                self._log.info("[PaymentSender] 选中收款码图片")
            else:
                sz = self.d.window_size()
                tap_x, tap_y = int(sz[0] * 0.15), int(sz[1] * 0.25)
                self.d.click(tap_x, tap_y)
                self._log.execute_rpa(tap_x, tap_y)
                self._log.warning("[PaymentSender] 缩略图 xpath 未找到，使用坐标")
            time.sleep(0.5)

            send_btn = self.d.xpath('//*[@content-desc="发送"] | //*[@resource-id="com.tencent.mm:id/send"]')
            if send_btn.exists:
                send_btn.click()
                self._log.execute_rpa(self.input_x + 160, self.input_y)
                self._log.info(f"[PaymentSender] ✅ 收款码图片已发送，金额={price}元")
                time.sleep(0.3)
                return True

            self.d.press("back")
            self._log.warning("[PaymentSender] 发送按钮未找到")
            return False
        except Exception as e:
            self._log.error(f"[PaymentSender] 图片发送异常: {e}")
            try:
                self.d.press("back")
            except Exception:
                pass
            return False

    def _try_send_text(self, price: float) -> bool:
        try:
            msg = f"兄弟，麻烦扫一下收款码，总计 {price:.0f} 元，谢谢！"
            self.d.click(self.input_x, self.input_y)
            self._log.execute_rpa(self.input_x, self.input_y)
            time.sleep(settings.INPUT_DELAY_BEFORE)
            self.d.send_keys(msg)
            time.sleep(settings.INPUT_DELAY_AFTER)
            self.d.press("enter")
            self._log.info(f"[PaymentSender] ✅ 文字降级发送: {msg}")
            return True
        except Exception as e:
            self._log.error(f"[PaymentSender] 文字发送失败: {e}")
            return False
