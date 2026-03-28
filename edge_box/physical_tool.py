"""
edge_box/physical_tool.py
Project Claw - 物理执行唯一入口（重构版）

规范（.cursorrules）：
- 严禁直接调用 d.click / u2.connect
- 所有物理操作必须通过 BaseDriver 抽象基类
"""
from __future__ import annotations

import logging
from typing import Optional

from edge_box.base_driver import BaseDriver, get_driver

logger = logging.getLogger("claw.edge.physical_tool")


def notify_and_send_qrcode(
    price: float,
    reply: Optional[str] = None,
    driver: Optional[BaseDriver] = None,
) -> bool:
    """
    物理执行入口：通过 BaseDriver 打开微信收款界面 + 发送确认消息。

    Args:
        price:  成交金额（元）
        reply:  发给客户的文字消息（默认自动生成）
        driver: 可注入 BaseDriver 实例（测试/复用），默认自动检测

    Returns:
        bool: 执行是否成功
    """
    if driver is None:
        driver = get_driver()

    if not driver.is_connected():
        logger.error("[physical_tool] 设备未连接")
        return False

    msg = reply or f"接单成功！收款金额 ¥{price:.1f} 元，请扫码支付"

    try:
        # 1. 打开微信固定金额收款界面
        ok = driver.open_wechat_receive_money(price)
        if not ok:
            logger.warning("[physical_tool] 打开收款界面失败，降级发文本消息")

        # 2. 发送确认消息
        driver.send_wechat_message(msg)
        logger.info(f"[physical_tool] 消息已发送 ¥{price}")
        return True

    except Exception as e:
        logger.error(f"[physical_tool] notify_and_send_qrcode 失败: {e}")
        return False
