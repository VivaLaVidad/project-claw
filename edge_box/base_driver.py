"""
edge_box/base_driver.py
Project Claw - BaseDriver 抽象基类 + U2Driver 实现

规范（来自 .cursorrules）：
- 严禁在业务逻辑中直接调用 d.click 或 u2.connect
- 所有物理操作必须通过 BaseDriver 抽象基类进行
- U2Driver 是当前实现，未来预留 AccessibilityDriver 接口
"""
from __future__ import annotations

import abc
import io
import logging
import time
from typing import Optional, Tuple

logger = logging.getLogger("claw.edge.driver")


# ─── BaseDriver 抽象基类 ──────────────────────────────────────────────────────
class BaseDriver(abc.ABC):
    """所有设备驱动的抽象基类。业务层只允许调用此接口。"""

    @abc.abstractmethod
    def get_screenshot(self) -> bytes:
        """截取当前屏幕，返回 PNG 字节流。"""

    @abc.abstractmethod
    def tap(self, x: float, y: float) -> None:
        """点击屏幕坐标 (x, y)。"""

    @abc.abstractmethod
    def swipe_down_notification(self) -> None:
        """下拉通知栏。"""

    @abc.abstractmethod
    def send_text(self, text: str) -> None:
        """向当前焦点输入框发送文本。"""

    @abc.abstractmethod
    def generate_payment_qr(
        self,
        amount_yuan: float,
        description: str = "Project Claw 收款",
    ) -> str:
        """
        生成指定固定金额的收款码/支付链接。
        返回：二维码图片路径或支付链接 URL。
        """

    @abc.abstractmethod
    def send_wechat_message(self, text: str) -> bool:
        """在微信当前对话中发送一条消息。"""

    @abc.abstractmethod
    def open_wechat_receive_money(
        self,
        amount_yuan: float,
    ) -> bool:
        """
        打开微信「收款」界面并设置固定金额。
        返回是否成功打开。
        """

    @abc.abstractmethod
    def is_connected(self) -> bool:
        """检查设备连接状态。"""


# ─── U2Driver 实现（uiautomator2）─────────────────────────────────────────────
class U2Driver(BaseDriver):
    """
    基于 uiautomator2 的 Android 设备驱动。
    生产实现，连接真实 Android 设备。
    """

    def __init__(self, device_serial: Optional[str] = None):
        self._serial = device_serial
        self._d = None  # uiautomator2 device 实例（懒加载）

    @classmethod
    def connect(cls, device_serial: Optional[str] = None) -> "U2Driver":
        """工厂方法：连接设备并返回 Driver 实例。"""
        driver = cls(device_serial)
        driver._ensure_connected()
        return driver

    def _ensure_connected(self) -> None:
        if self._d is not None:
            return
        try:
            import uiautomator2 as u2
            self._d = u2.connect(self._serial) if self._serial else u2.connect()
            logger.info(f"[U2Driver] 已连接设备: {self._d.serial}")
        except ImportError:
            logger.warning("[U2Driver] uiautomator2 未安装，使用 MockDriver")
            raise RuntimeError("uiautomator2 不可用，请使用 MockDriver")

    def get_screenshot(self) -> bytes:
        self._ensure_connected()
        img = self._d.screenshot(format="pillow")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def tap(self, x: float, y: float) -> None:
        self._ensure_connected()
        self._d.click(x, y)
        logger.debug(f"[U2Driver] tap({x:.1f}, {y:.1f})")

    def swipe_down_notification(self) -> None:
        self._ensure_connected()
        self._d.open_notification()
        time.sleep(0.8)

    def send_text(self, text: str) -> None:
        self._ensure_connected()
        self._d.send_keys(text)

    def generate_payment_qr(
        self,
        amount_yuan: float,
        description: str = "Project Claw 收款",
    ) -> str:
        """
        打开微信收款并截图保存二维码。
        返回截图保存路径。
        """
        self.open_wechat_receive_money(amount_yuan)
        time.sleep(1.5)
        png = self.get_screenshot()
        path = f"/tmp/payment_qr_{int(time.time())}.png"
        with open(path, "wb") as f:
            f.write(png)
        logger.info(f"[U2Driver] 收款码截图保存: {path}")
        return path

    def send_wechat_message(self, text: str) -> bool:
        try:
            self._ensure_connected()
            # 点击微信输入框（坐标为示例，实际需根据分辨率调整）
            self._d(resourceId="com.tencent.mm:id/b5z").set_text(text)
            self._d(resourceId="com.tencent.mm:id/b60").click()
            return True
        except Exception as e:
            logger.error(f"[U2Driver] send_wechat_message failed: {e}")
            return False

    def open_wechat_receive_money(self, amount_yuan: float) -> bool:
        try:
            self._ensure_connected()
            # 启动微信收款 Activity
            self._d.app_start("com.tencent.mm",
                              ".plugin.collect.ui.CollectMainUI",
                              wait=True)
            time.sleep(1.2)
            # 点击「设置金额」
            el = self._d(text="设置金额")
            if el.exists(timeout=3):
                el.click()
                time.sleep(0.5)
                self._d.send_keys(str(int(amount_yuan * 100)))  # 分
            logger.info(f"[U2Driver] 微信收款界面已打开 ¥{amount_yuan}")
            return True
        except Exception as e:
            logger.error(f"[U2Driver] open_wechat_receive_money failed: {e}")
            return False

    def is_connected(self) -> bool:
        try:
            self._ensure_connected()
            return self._d is not None
        except Exception:
            return False


# ─── MockDriver（无设备环境 / Railway CI / 测试）──────────────────────────────
class MockDriver(BaseDriver):
    """
    无 Android 设备时的 Mock 实现。
    所有截图返回空白 PNG，所有操作记录日志但不执行。
    """

    _BLANK_PNG = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
        b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18"
        b"\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    def get_screenshot(self) -> bytes:
        logger.debug("[MockDriver] get_screenshot -> blank PNG")
        return self._BLANK_PNG

    def tap(self, x: float, y: float) -> None:
        logger.info(f"[MockDriver] tap({x:.1f}, {y:.1f})")

    def swipe_down_notification(self) -> None:
        logger.info("[MockDriver] swipe_down_notification")

    def send_text(self, text: str) -> None:
        logger.info(f"[MockDriver] send_text: {text!r}")

    def generate_payment_qr(self, amount_yuan: float, description: str = "") -> str:
        path = f"/tmp/mock_payment_qr_{int(time.time())}.png"
        logger.info(f"[MockDriver] generate_payment_qr ¥{amount_yuan} -> {path}")
        return path

    def send_wechat_message(self, text: str) -> bool:
        logger.info(f"[MockDriver] send_wechat_message: {text!r}")
        return True

    def open_wechat_receive_money(self, amount_yuan: float) -> bool:
        logger.info(f"[MockDriver] open_wechat_receive_money ¥{amount_yuan}")
        return True

    def is_connected(self) -> bool:
        return True


# ─── 工厂函数 ─────────────────────────────────────────────────────────────────
def get_driver(device_serial: Optional[str] = None) -> BaseDriver:
    """
    自动选择 Driver：
    - 有 uiautomator2 且有设备 → U2Driver
    - 否则 → MockDriver（云端/CI 环境）
    """
    try:
        return U2Driver.connect(device_serial)
    except Exception:
        logger.warning("[Driver] 回退到 MockDriver（无 Android 设备）")
        return MockDriver()
