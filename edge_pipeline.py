from __future__ import annotations

import hashlib
import re
import time
from collections import deque
from typing import List

import cv2
import numpy as np

from config import settings
from logger_setup import setup_logger

logger = setup_logger("claw.pipeline")


class BubbleDetector:
    def __init__(self):
        self.bot_lower = np.array([35, 80, 100])
        self.bot_upper = np.array([85, 255, 255])

    def is_user_message(self, bbox: List, img: np.ndarray) -> bool:
        try:
            xs = [p[0] for p in bbox]
            ys = [p[1] for p in bbox]
            x1 = max(0, int(min(xs)) - 10)
            x2 = min(img.shape[1], int(max(xs)) + 10)
            y1 = max(0, int(min(ys)) - 10)
            y2 = min(img.shape[0], int(max(ys)) + 10)
            region = img[y1:y2, x1:x2]
            if region.size == 0:
                return True
            hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
            ratio = np.count_nonzero(cv2.inRange(hsv, self.bot_lower, self.bot_upper)) / hsv[:, :, 0].size
            return ratio <= 0.2
        except Exception:
            return True


class MessageExtractor:
    UI_NOISE = {
        "发送", "表情", "语音", "微信", "限制", "下午", "上午",
        "拍摄", "相册", "位置", "视频通话", "通话", "搜索", "更多",
    }
    TIME_TAG_PATTERNS = [
        re.compile(r"^(周[一二三四五六日天]|星期[一二三四五六日天])\s*\d{1,2}[:：]\d{2}$"),
        re.compile(r"^\d{1,2}月\d{1,2}日\s*\d{1,2}[:：]\d{2}$"),
        re.compile(r"^\d{4}[/-]\d{1,2}[/-]\d{1,2}(\s+\d{1,2}[:：]\d{2})?$"),
    ]

    def __init__(self):
        self.last_text = ""
        self.last_bbox = None

    def clean(self, text: str) -> str:
        return re.sub(r"\s+", " ", text.replace("\n", " ").replace("\r", " ")).strip()

    def is_noise(self, text: str) -> bool:
        if not text:
            return True
        if text in self.UI_NOISE or any(k in text for k in self.UI_NOISE):
            return True
        if re.fullmatch(r"\d{1,2}[:：.]\d{2}", text):
            return True
        if any(p.fullmatch(text) for p in self.TIME_TAG_PATTERNS):
            return True
        if len(text) == 1 and not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", text):
            return True
        if re.fullmatch(r"[^\u4e00-\u9fffA-Za-z0-9]+", text):
            return True
        if len(text) <= 2 and text.isdigit():
            return True
        return False

    def bbox_bottom(self, bbox) -> float:
        return max(p[1] for p in bbox) if bbox else 0

    def is_new(self, text: str, bbox) -> bool:
        if text != self.last_text:
            return True
        if self.last_bbox is None:
            return True
        return abs(self.bbox_bottom(bbox) - self.bbox_bottom(self.last_bbox)) > settings.MESSAGE_BBOX_DISTANCE_THRESHOLD

    def extract(self, results, crop_left, crop_top, img, bubble: BubbleDetector) -> str:
        candidates = []
        for bbox, text, prob in results:
            text = self.clean(text)
            if self.is_noise(text):
                continue
            mapped = [[p[0] + crop_left, p[1] + crop_top] for p in bbox]
            if not bubble.is_user_message(mapped, img):
                continue
            bottom = self.bbox_bottom(mapped)
            candidates.append((bottom, prob, text, mapped))
        if not candidates:
            return ""
        candidates.sort(key=lambda x: x[0], reverse=True)
        for bottom, prob, text, bbox in candidates:
            if self.is_new(text, bbox):
                self.last_text = text
                self.last_bbox = bbox
                logger.vision_scan(text)
                return text
        return ""


class MessageDedup:
    def __init__(self, window: int = 50, time_window: int = 120):
        self.cache = deque(maxlen=window)
        self.tw = time_window

    def _normalize(self, text: str) -> str:
        text = text.strip()
        text = re.sub(r"\s+", "", text)
        text = re.sub(r"[，。！？!?,.；;：:~`\-—_（）()\[\]{}<>《》\"'“”‘’]", "", text)
        return text

    def add(self, text: str):
        norm = self._normalize(text)
        self.cache.append({"h": hashlib.md5(norm.encode()).hexdigest(), "t": time.time()})

    def is_dup(self, text: str) -> bool:
        norm = self._normalize(text)
        h = hashlib.md5(norm.encode()).hexdigest()
        now = time.time()
        return any(i["h"] == h and now - i["t"] < self.tw for i in self.cache)
