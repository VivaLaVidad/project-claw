"""
Project Claw v3.0 - 去中心化 Agent 执行中台
集成 CV + LLM + RAG + Anti-Ban RPA
"""
import os, sys, time, logging, hashlib, random, json
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple, List
from dataclasses import dataclass, field
from collections import deque
from pathlib import Path
from enum import Enum
import cv2, numpy as np, yaml, requests, easyocr
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from edge_driver import U2Driver

try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False

try:
    import chromadb
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False


def setup_logger(cfg):
    lc = cfg.get('logging', {})
    level = getattr(logging, lc.get('level', 'INFO'))
    log_file = lc.get('file', 'logs/lobster.log')
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger('Lobster')
    if logger.handlers:
        return logger
    logger.setLevel(level)
    from logging.handlers import RotatingFileHandler
    fmt = logging.Formatter(lc.get('format', '%(asctime)s [%(levelname)s] %(message)s'))
    fh = RotatingFileHandler(log_file, maxBytes=lc.get('max_bytes', 10485760),
                             backupCount=lc.get('backup_count', 3))
    fh.setFormatter(fmt)
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


class MsgStatus(Enum):
    PENDING  = 'pending'
    REPLIED  = 'replied'
    FAILED   = 'failed'
    FILTERED = 'filtered'


@dataclass
class Message:
    content: str
    timestamp: datetime
    hash: str = field(default='')
    status: MsgStatus = field(default=MsgStatus.PENDING)
    reply: Optional[str] = field(default=None)
    def __post_init__(self):
        if not self.hash:
            self.hash = hashlib.md5(self.content.encode()).hexdigest()


@dataclass
class Stats:
    total: int = 0
    replied: int = 0
    filtered: int = 0
    failed: int = 0
    input_failed: int = 0
    started: datetime = field(default_factory=datetime.now)
    def uptime(self):
        s = int((datetime.now() - self.started).total_seconds())
        return f'{s//3600}h{s%3600//60}m{s%60}s'
    def __str__(self):
        return f'总:{self.total} 回:{self.replied} 滤:{self.filtered} 败:{self.failed} 输入失败:{self.input_failed} 时:{self.uptime()}'


class Config:
    def __init__(self, path='config.yaml'):
        with open(path, 'r', encoding='utf-8') as f:
            self._cfg = yaml.safe_load(f)
    def get(self, *keys, default=None):
        v = self._cfg
        for k in keys:
            if not isinstance(v, dict): return default
            v = v.get(k)
        return v if v is not None else default


class DeepSeekClient:
    def __init__(self, cfg, logger):
        self.cfg = cfg
        self.logger = logger
        self.key = cfg.get('api', 'api_key', default='') or os.getenv('DEEPSEEK_API_KEY', '')
        if not self.key:
            raise ValueError('请在 config.yaml 的 api.api_key 中填入 DeepSeek API Key')
        s = requests.Session()
        retry = Retry(total=cfg.get('api', 'max_retries', default=3),
                      backoff_factor=cfg.get('api', 'retry_delay', default=1),
                      status_forcelist=[429, 500, 502, 503, 504],
                      allowed_methods=['POST'])
        s.mount('https://', HTTPAdapter(max_retries=retry))
        s.mount('http://',  HTTPAdapter(max_retries=retry))
        self.session = s

    def ask(self, message):
        try:
            url = self.cfg.get('api', 'base_url', default='https://api.deepseek.com') + '/chat/completions'
            r = self.session.post(url, json={
                'model': self.cfg.get('api', 'model', default='deepseek-chat'),
                'messages': [
                    {'role': 'system', 'content': self.cfg.get('reply', 'system_prompt', default='')},
                    {'role': 'user',   'content': message}
                ],
                'temperature': 0.7,
                'max_tokens': self.cfg.get('reply', 'max_tokens', default=80)
            }, headers={'Authorization': f'Bearer {self.key}', 'Content-Type': 'application/json'},
               timeout=self.cfg.get('api', 'timeout', default=10))
            r.raise_for_status()
            return r.json()['choices'][0]['message']['content'].strip()
        except requests.exceptions.Timeout:
            self.logger.error('API 超时')
        except requests.exceptions.RequestException as e:
            self.logger.error(f'API 请求失败: {e}')
        except Exception as e:
            self.logger.error(f'API 异常: {e}')
        return None


class AntibanInput:
    """
    拟人化输入模块：
    1. 贝塞尔曲线轨迹点击
    2. 随机键入延迟
    3. 多种输入降级方案
    """
    def __init__(self, device, logger):
        self.device = device
        self.logger = logger

    @staticmethod
    def _bezier_curve(p0, p1, p2, p3, steps=20):
        """生成贝塞尔曲线轨迹点"""
        points = []
        for i in range(steps):
            t = i / steps
            mt = 1 - t
            x = (mt**3 * p0[0] + 3*mt**2*t * p1[0] + 3*mt*t**2 * p2[0] + t**3 * p3[0])
            y = (mt**3 * p0[1] + 3*mt**2*t * p1[1] + 3*mt*t**2 * p2[1] + t**3 * p3[1])
            points.append((int(x), int(y)))
        return points

    def human_click(self, x, y):
        """拟人化点击：贝塞尔曲线轨迹"""
        try:
            # 生成随机控制点，制造自然轨迹
            cx1 = x + random.randint(-50, 50)
            cy1 = y + random.randint(-50, 50)
            cx2 = x + random.randint(-50, 50)
            cy2 = y + random.randint(-50, 50)
            points = self._bezier_curve((x, y), (cx1, cy1), (cx2, cy2), (x, y), steps=10)
            # 沿轨迹移动（如果设备支持）
            for px, py in points:
                time.sleep(random.uniform(0.01, 0.05))
            self.device.click(x, y)
            self.logger.debug(f'拟人化点击: ({x}, {y})')
        except Exception as e:
            self.logger.warning(f'拟人化点击失败，降级普通点击: {e}')
            self.device.click(x, y)

    def human_type(self, text):
        """
        拟人化输入文字：
        1. 尝试 ADB 键盘输入（最快）
        2. 尝试剪贴板 + 粘贴
        3. 尝试 set_text
        4. 最后回退到 send_keys
        """
        # 方案1：ADB 键盘输入（绕过安全限制）
        try:
            self.device.shell(f'input text "{text}"')
            self.logger.debug('ADB input text 成功')
            return True
        except Exception as e:
            self.logger.debug(f'ADB input text 失败: {e}')

        # 方案2：剪贴板 + 粘贴
        try:
            self.device.set_clipboard(text)
            time.sleep(random.uniform(0.2, 0.4))
            self.device.press('ctrl', 'v')
            self.logger.debug('剪贴板粘贴成功')
            return True
        except Exception as e:
            self.logger.debug(f'剪贴板粘贴失败: {e}')

        # 方案3：set_text
        try:
            edit = self.device.selector(className='android.widget.EditText')
            if edit.exists:
                edit.set_text(text)
                self.logger.debug('set_text 成功')
                return True
        except Exception as e:
            self.logger.debug(f'set_text 失败: {e}')

        # 方案4：send_keys（最慢但最兼容）
        try:
            self.device.send_keys(text)
            self.logger.debug('send_keys 成功')
            return True
        except Exception as e:
            self.logger.error(f'所有输入方式均失败: {e}')
            return False


class YOLODetector:
    def __init__(self, cfg, logger):
        self.logger  = logger
        self.model   = None
        self.conf    = cfg.get('yolo', 'confidence', default=0.5)
        self.cls_inp = cfg.get('yolo', 'classes', 'input_box',   default=0)
        self.cls_snd = cfg.get('yolo', 'classes', 'send_button', default=1)
        if cfg.get('yolo', 'enabled', default=True) and YOLO_AVAILABLE:
            mp = cfg.get('yolo', 'model_path', default='yolo_ui.pt')
            if Path(mp).exists():
                try:
                    self.model = YOLO(mp)
                    self.logger.info(f'YOLO 已加载: {mp}')
                except Exception as e:
                    self.logger.warning(f'YOLO 加载失败，降级OCR: {e}')
            else:
                self.logger.warning(f'YOLO模型不存在({mp})，使用OCR降级')

    def detect(self, img):
        res = {'input_box': None, 'send_button': None}
        if self.model is None:
            return res
        try:
            for box in self.model(img, conf=self.conf, verbose=False)[0].boxes:
                cls = int(box.cls[0])
                x0, y0, x1, y1 = box.xyxy[0].cpu().numpy().astype(int)
                cx, cy = (x0+x1)//2, (y0+y1)//2
                if   cls == self.cls_inp: res['input_box']   = (cx, cy)
                elif cls == self.cls_snd: res['send_button'] = (cx, cy)
        except Exception as e:
            self.logger.error(f'YOLO推理失败: {e}')
        return res

    def find_send_in_roi(self, img, ratio):
        h = img.shape[0]
        top = int(h * ratio)
        res = self.detect(img[top:, :])
        if res['send_button']:
            cx, cy = res['send_button']
            return cx, cy + top
        return None


class OCRExtractor:
    def __init__(self, cfg, logger):
        self.logger   = logger
        self.kw       = cfg.get('filter', 'keywords',              default=[])
        self.min_len  = cfg.get('filter', 'min_length',            default=2)
        self.max_len  = cfg.get('filter', 'max_length',            default=300)
        self.min_prob = cfg.get('ocr',    'min_prob',              default=0.5)
        self.top_r    = cfg.get('ocr',    'msg_roi_top_ratio',     default=0.15)
        self.bot_r    = cfg.get('ocr',    'msg_roi_bottom_ratio',  default=0.82)
        langs = cfg.get('ocr', 'languages', default=['ch_sim', 'en'])
        self.logger.info('初始化 EasyOCR...')
        self.reader = easyocr.Reader(langs, gpu=False)
        self.logger.info('EasyOCR 就绪')

    def extract_message(self, img):
        try:
            h = img.shape[0]
            roi = img[int(h*self.top_r):int(h*self.bot_r), :]
            for (_, text, prob) in reversed(self.reader.readtext(roi, detail=1)):
                text = text.strip()
                if prob < self.min_prob: continue
                if not (self.min_len <= len(text) <= self.max_len): continue
                if any(k in text for k in self.kw): continue
                return text
        except Exception as e:
            self.logger.error(f'OCR提取失败: {e}')
        return None

    def find_send_ocr(self, img, ratio):
        try:
            h = img.shape[0]
            top = int(h * ratio)
            for (bbox, text, _) in self.reader.readtext(img[top:, :], detail=1):
                if '发送' in text:
                    cx = int((bbox[0][0] + bbox[2][0]) / 2)
                    cy = int((bbox[0][1] + bbox[2][1]) / 2)
                    return cx, cy + top
        except Exception as e:
            self.logger.error(f'OCR找发送按钮失败: {e}')
        return None


class VisualConfirm:
    def __init__(self, cfg, logger):
        self.logger    = logger
        self.enabled   = cfg.get('visual_confirm', 'enabled',        default=True)
        self.max_wait  = cfg.get('visual_confirm', 'max_wait',       default=3.0)
        self.poll      = cfg.get('visual_confirm', 'poll_interval',  default=0.3)
        self.threshold = cfg.get('visual_confirm', 'diff_threshold', default=0.02)

    @staticmethod
    def _diff(a, b):
        a_ = cv2.resize(a, (320, 568))
        b_ = cv2.resize(b, (320, 568))
        gray = cv2.cvtColor(cv2.absdiff(a_, b_), cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(gray, 15, 255, cv2.THRESH_BINARY)
        return float(np.count_nonzero(mask)) / mask.size

    def wait_for_change(self, device, before, shot_path):
        if not self.enabled:
            return True
        deadline = time.time() + self.max_wait
        while time.time() < deadline:
            time.sleep(self.poll)
            try:
                device.screenshot(shot_path)
                after = cv2.imread(shot_path)
                r = self._diff(before, after)
                self.logger.debug(f'视觉差异: {r:.4f}')
                if r >= self.threshold:
                    self.logger.info(f'视觉确认: 界面已变化 diff={r:.3f}')
                    return True
            except Exception as e:
                self.logger.warning(f'视觉确认异常: {e}')
        self.logger.warning('视觉确认超时')
        return False


class DedupCache:
    def __init__(self, window_sec=30):
        self.window = timedelta(seconds=window_sec)
        self.cache = deque(maxlen=200)

    def is_dup(self, msg):
        now = datetime.now()
        while self.cache and (now - self.cache[0].timestamp) > self.window:
            self.cache.popleft()
        for m in self.cache:
            if m.hash == msg.hash:
                return True
        self.cache.append(msg)
        return False

class LobsterBot:
    def __init__(self, config_path='config.yaml'):
        self.cfg    = Config(config_path)
        self.logger = setup_logger(self.cfg._cfg)
        self.logger.info('=== Project Claw v3.0 启动 ===')
        ip = self.cfg.get('device', 'ip', default='')
        self.device = U2Driver.connect(ip) if ip else U2Driver.connect()
        self.logger.info('设备已连接')
        self.screen_w, self.screen_h = self.device.window_size()
        self.shot_path = self.cfg.get('device', 'screenshot_path', default='current_screen.png')
        self.send_shot = self.cfg.get('device', 'check_send_path',  default='check_send.png')
        self.api     = DeepSeekClient(self.cfg, self.logger)
        self.ocr     = OCRExtractor(self.cfg, self.logger)
        self.yolo    = YOLODetector(self.cfg, self.logger)
        self.confirm = VisualConfirm(self.cfg, self.logger)
        self.dedup   = DedupCache(self.cfg.get('security', 'dedup_window', default=30))
        self.antiban = AntibanInput(self.device, self.logger)
        self.stats          = Stats()
        self.last_text      = ''
        self.failures       = 0
        self.cooldown_until = None
        self.roi_ratio      = self.cfg.get('yolo', 'send_btn_roi_ratio', default=0.75)

    def _screenshot(self):
        self.device.screenshot(self.shot_path)
        return cv2.imread(self.shot_path)

    def _find_send_button(self, img):
        pos = self.yolo.find_send_in_roi(img, self.roi_ratio)
        if pos: return pos
        pos = self.ocr.find_send_ocr(img, self.roi_ratio)
        if pos: return pos
        return (int(self.screen_w * 0.88), self.screen_h - 60)

    def _click_input(self, img):
        try:
            edit = self.device.selector(className='android.widget.EditText')
            if edit.exists:
                cx, cy = edit.center()
                self.antiban.human_click(cx, cy)
                return
        except: pass
        res = self.yolo.detect(img)
        if res['input_box']:
            self.antiban.human_click(*res['input_box'])
            return
        self.antiban.human_click(self.screen_w // 2, self.screen_h - 150)

    def _click_send_button(self, img):
        try:
            btn = self.device.selector(text='发送')
            if btn.exists:
                self.antiban.human_click(*btn.center())
                return True
        except: pass
        pos = self._find_send_button(img)
        if pos:
            self.antiban.human_click(*pos)
            return True
        self.device.press('enter')
        return True

    def _send_reply(self, reply):
        try:
            before_input = self._screenshot()
            self._click_input(before_input)
            time.sleep(random.uniform(*self.cfg.get('reply', 'input_delay', default=[0.3, 0.6])))
            ok_input = self.antiban.human_type(reply)
            if not ok_input:
                self.stats.input_failed += 1
                return False
            time.sleep(random.uniform(*self.cfg.get('reply', 'send_delay', default=[0.8, 1.2])))
            img_after = self._screenshot()
            before_send = self._screenshot()
            self._click_send_button(img_after)
            ok = self.confirm.wait_for_change(self.device, before_send, self.send_shot)
            if ok:
                self.logger.info(f'发送成功: {reply}')
            else:
                self.device.press('enter')
            return ok
        except Exception as e:
            self.logger.error(f'_send_reply 异常: {e}', exc_info=True)
            return False

    def _in_cooldown(self):
        if self.cooldown_until and datetime.now() < self.cooldown_until:
            return True
        self.cooldown_until = None
        return False

    def run(self):
        interval = self.cfg.get('reply', 'check_interval', default=2)
        max_fail = self.cfg.get('security', 'max_failures',  default=5)
        cool_sec = self.cfg.get('security', 'cooldown_time', default=120)
        self.logger.info(f'开始监听，间隔 {interval}s')
        try:
            while True:
                if self._in_cooldown():
                    time.sleep(interval)
                    continue
                try:
                    img  = self._screenshot()
                    text = self.ocr.extract_message(img)
                    if text and text != self.last_text:
                        msg = Message(content=text, timestamp=datetime.now())
                        if self.dedup.is_dup(msg):
                            self.last_text = text
                            time.sleep(interval)
                            continue
                        self.logger.info(f'新消息: {text}')
                        self.stats.total += 1
                        reply = self.api.ask(text)
                        if reply:
                            ok = self._send_reply(reply)
                            if ok:
                                self.stats.replied += 1
                                self.failures = 0
                                self.dedup.is_dup(Message(content=reply, timestamp=datetime.now()))
                            else:
                                self.stats.failed += 1
                                self.failures += 1
                        else:
                            self.stats.failed += 1
                            self.failures += 1
                        self.last_text = text
                    else:
                        self.stats.filtered += 1
                    if self.failures >= max_fail:
                        self.cooldown_until = datetime.now() + timedelta(seconds=cool_sec)
                        self.logger.warning(f'连续失败{self.failures}次，冷却{cool_sec}s')
                        self.failures = 0
                except Exception as e:
                    self.logger.error(f'主循环异常: {e}', exc_info=True)
                    self.failures += 1
                time.sleep(interval)
        except KeyboardInterrupt:
            self.logger.info(f'已停止。统计: {self.stats}')


def main():
    LobsterBot('config.yaml').run()


if __name__ == '__main__':
    main()
 