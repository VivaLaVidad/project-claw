from __future__ import annotations

from dataclasses import dataclass

from config import settings
from edge_driver import BaseDriver
from edge_execution import PaymentSender, UIVerifier


@dataclass
class ScreenGeometry:
    width: int
    height: int
    input_x: float
    input_y: float
    crop_top: int
    crop_bottom: int
    crop_left: int
    crop_right: int

    @classmethod
    def from_driver(cls, driver: BaseDriver) -> "ScreenGeometry":
        width, height = driver.window_size()
        return cls(
            width=width,
            height=height,
            input_x=width / 2,
            input_y=height - settings.INPUT_Y_OFFSET,
            crop_top=int(height * settings.CROP_TOP_RATIO),
            crop_bottom=int(height * settings.CROP_BOTTOM_RATIO),
            crop_left=int(width * settings.CROP_LEFT_RATIO),
            crop_right=int(width * settings.CROP_RIGHT_RATIO),
        )


class EdgeRuntimeContext:
    def __init__(self, driver: BaseDriver, payment_qr_path: str):
        self.driver = driver
        self.geometry = ScreenGeometry.from_driver(driver)
        self.verifier = UIVerifier(
            device=driver,
            timeout=settings.UI_VERIFY_TIMEOUT,
            max_retries=settings.UI_VERIFY_MAX_RETRIES,
        )
        self.payment_sender = PaymentSender(
            device=driver,
            input_x=self.geometry.input_x,
            input_y=self.geometry.input_y,
            qr_path=payment_qr_path,
        )

    def update_driver(self, driver: BaseDriver) -> None:
        self.driver = driver
        self.geometry = ScreenGeometry.from_driver(driver)
        self.verifier.set_driver(driver)
        self.payment_sender.set_driver(driver)
        self.payment_sender.set_input_position(
            self.geometry.input_x,
            self.geometry.input_y,
        )
