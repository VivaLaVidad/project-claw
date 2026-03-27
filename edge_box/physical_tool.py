from __future__ import annotations

from edge_driver import U2Driver
from edge_execution import PaymentSender, UIVerifier
from edge_runtime import EdgeRuntimeContext
from config import settings


def notify_and_send_qrcode(price: float) -> bool:
    """物理执行唯一入口：唤醒微信并发送接单成功消息 + 收款码。"""

    driver = U2Driver.connect()
    ctx = EdgeRuntimeContext(driver=driver, payment_qr_path=settings.PAYMENT_QR_PATH)

    reply = f"接单成功，金额 {float(price):.0f} 元"
    ok = ctx.verifier.send_with_verify(
        input_x=ctx.geometry.input_x,
        input_y=ctx.geometry.input_y,
        reply=reply,
    )
    if not ok:
        return False
    return ctx.payment_sender.send_payment_code(float(price))
