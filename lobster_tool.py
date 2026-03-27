"""
LobsterPhysicalTool - 微信自动化视觉点击工具
基于 uiautomator2 和 easyocr 的物理外挂
"""
import easyocr
import cv2
import numpy as np
import time
import random
from typing import Optional

from edge_driver import BaseDriver, U2Driver
from logger_setup import setup_logger

logger = setup_logger(__name__)


class LobsterPhysicalTool:
    """龙虾物理工具类：封装微信自动化视觉点击流程"""
    
    def __init__(self, device_ip: str = None, driver: Optional[BaseDriver] = None):
        """初始化工具"""
        self.device = driver or U2Driver.connect(device_ip)
        self.reader = easyocr.Reader(['ch_sim', 'en'])
        self.w, self.h = self.device.window_size()
        
        self.user_bubble_lower = np.array([0, 0, 80])
        self.user_bubble_upper = np.array([180, 50, 220])
        self.bot_bubble_lower = np.array([35, 80, 100])
        self.bot_bubble_upper = np.array([85, 255, 255])
        
        logger.info(f"✅ 龙虾物理工具已初始化 | 屏幕: {self.w}x{self.h}")

    def get_latest_message(self) -> Optional[str]:
        """获取最新的用户消息（左边灰色气泡）"""
        try:
            img_path = "current_screen.png"
            self.device.screenshot(img_path)
            img = cv2.imread(img_path)
            results = self.reader.readtext(img_path, detail=1)
            
            for (bbox, text, prob) in reversed(results):
                text = text.strip()
                
                if len(text) < 1:
                    continue
                if any(bad in text for bad in ["发送", "表情", "语音", "微信", "限制", "下午", "上午"]):
                    continue
                
                if not self._is_user_message(bbox, img):
                    logger.debug(f"🚫 过滤龙虾回复: {text}")
                    continue

                logger.vision_scan(text)
                logger.info(f"📨 获取消息: {text}")
                return text
            
            return None
        
        except Exception as e:
            logger.error(f"❌ 获取消息异常: {e}")
            return None

    def send_wechat_message(self, text: str) -> bool:
        """发送微信消息"""
        try:
            logger.info(f"📤 准备发送: {text}")
            
            input_x, input_y = self.w / 2, self.h - 150
            self.device.click(input_x, input_y)
            logger.execute_rpa(input_x, input_y)
            time.sleep(random.uniform(0.5, 1.0))
            
            self.device.send_keys(text)
            time.sleep(random.uniform(1.0, 2.0))
            
            self.device.screenshot("check_send.png")
            send_results = self.reader.readtext("check_send.png", detail=1)
            
            # 优化：支持多种发送按钮识别
            for (bbox, btn_text, prob) in send_results:
                btn_text_clean = btn_text.strip()
                if any(kw in btn_text_clean for kw in ["发送", "send", "Send"]):
                    send_x = (bbox[0][0] + bbox[2][0]) / 2
                    send_y = (bbox[0][1] + bbox[2][1]) / 2
                    self.device.click(send_x, send_y)
                    logger.execute_rpa(send_x, send_y)
                    logger.info(f"🚀 消息已发送（通过按钮）")
                    return True
            
            logger.warning("⚠️ 未找到发送按钮，尝试回车")
            self.device.press('enter')
            time.sleep(0.5)
            logger.info(f"🚀 消息已发送（通过回车）")
            return True
        
        except Exception as e:
            logger.error(f"❌ 发送消息异常: {e}")
            return False

    def _is_user_message(self, bbox, img) -> bool:
        """判断是否为用户消息（左边灰色气泡）"""
        try:
            x_coords = [p[0] for p in bbox]
            y_coords = [p[1] for p in bbox]
            x_min, x_max = int(min(x_coords)), int(max(x_coords))
            y_min, y_max = int(min(y_coords)), int(max(y_coords))
            
            x_min = max(0, x_min - 10)
            x_max = min(img.shape[1], x_max + 10)
            y_min = max(0, y_min - 10)
            y_max = min(img.shape[0], y_max + 10)
            
            bubble_region = img[y_min:y_max, x_min:x_max]
            
            if bubble_region.size == 0:
                return True
            
            hsv = cv2.cvtColor(bubble_region, cv2.COLOR_BGR2HSV)
            
            bot_mask = cv2.inRange(hsv, self.bot_bubble_lower, self.bot_bubble_upper)
            bot_ratio = np.count_nonzero(bot_mask) / bot_mask.size
            
            if bot_ratio > 0.2:
                return False
            
            return True
        
        except Exception as e:
            logger.debug(f"⚠️ 气泡检测异常: {e}，默认认为是用户消息")
            return True

    def take_screenshot(self, path: str = "screenshot.png") -> str:
        """截屏"""
        self.device.screenshot(path)
        return path
