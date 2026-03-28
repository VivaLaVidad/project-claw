"""physical_tool.py - VLM UI Grounding 架构"""
import asyncio, json, base64, time, logging, io, numpy as np
from typing import Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from PIL import Image

try:
    import uiautomator2 as u2
    HAS_U2 = True
except:
    HAS_U2 = False

try:
    import easyocr
    HAS_OCR = True
except:
    HAS_OCR = False

try:
    import httpx
    HAS_HTTPX = True
except:
    HAS_HTTPX = False

logger = logging.getLogger(__name__)

class VisionMode(str, Enum):
    LOCAL_VLM = "local_vlm"
    CLOUD_GPT4O = "cloud_gpt4o"
    CLOUD_DEEPSEEK = "cloud_deepseek"
    FALLBACK_OCR = "fallback_ocr"

@dataclass
class ScreenAnalysisResult:
    latest_message: Optional[str]
    input_box_pos: Optional[Tuple[int, int]]
    send_button_pos: Optional[Tuple[int, int]]
    mode: VisionMode
    raw_response: str
    timestamp: float

class OmniVisionAnalyzer:
    """全能视觉分析器 - VLM + 自动降级"""
    
    def __init__(self, device_id=None, gpt4o_api_key=None, deepseek_api_key=None, enable_local_vlm=False, timeout=10.0):
        self.device_id = device_id
        self.gpt4o_api_key = gpt4o_api_key
        self.deepseek_api_key = deepseek_api_key
        self.enable_local_vlm = enable_local_vlm
        self.timeout = timeout
        
        self.device = None
        if HAS_U2 and device_id:
            try:
                self.device = u2.connect(device_id)
                logger.info(f"Connected to device: {device_id}")
            except Exception as e:
                logger.warning(f"Failed to connect: {e}")
        
        self.ocr = None
        if HAS_OCR:
            try:
                self.ocr = easyocr.Reader(['ch_sim', 'en'])
                logger.info("EasyOCR initialized")
            except Exception as e:
                logger.warning(f"EasyOCR init failed: {e}")
        
        self.http_client = None
        if HAS_HTTPX:
            self.http_client = httpx.AsyncClient(timeout=timeout)
    
    async def analyze_screen(self) -> ScreenAnalysisResult:
        """分析屏幕"""
        screenshot = await self._take_screenshot()
        if screenshot is None:
            return await self._fallback_ocr_analysis()
        
        result = await self._try_vlm_analysis(screenshot)
        if result is not None:
            return result
        
        logger.warning("VLM failed, falling back to OCR")
        return await self._fallback_ocr_analysis(screenshot)
    
    async def _take_screenshot(self) -> Optional[Image.Image]:
        """截取屏幕"""
        try:
            if self.device is None:
                return None
            screenshot_bytes = self.device.screenshot(format='png')
            return Image.open(io.BytesIO(screenshot_bytes))
        except Exception as e:
            logger.error(f"Screenshot failed: {e}")
            return None
    
    async def _try_vlm_analysis(self, screenshot: Image.Image) -> Optional[ScreenAnalysisResult]:
        """尝试 VLM 分析"""
        if self.enable_local_vlm:
            result = await self._analyze_with_local_vlm(screenshot)
            if result: return result
        
        if self.gpt4o_api_key:
            result = await self._analyze_with_gpt4o(screenshot)
            if result: return result
        
        if self.deepseek_api_key:
            result = await self._analyze_with_deepseek(screenshot)
            if result: return result
        
        return None
    
    async def _analyze_with_local_vlm(self, screenshot: Image.Image) -> Optional[ScreenAnalysisResult]:
        """本地 VLM"""
        try:
            logger.info("Local VLM analyzing...")
            return None
        except Exception as e:
            logger.error(f"Local VLM failed: {e}")
            return None
    
    async def _analyze_with_gpt4o(self, screenshot: Image.Image) -> Optional[ScreenAnalysisResult]:
        """GPT-4o 分析"""
        try:
            if not HAS_HTTPX or not self.http_client:
                return None
            
            img_bytes = io.BytesIO()
            screenshot.save(img_bytes, format='PNG')
            img_base64 = base64.b64encode(img_bytes.getvalue()).decode()
            
            response = await asyncio.wait_for(
                self.http_client.post(
                    "https://api.openai.com/v1/chat/completions",
                    json={
                        "model": "gpt-4-vision-preview",
                        "messages": [{
                            "role": "user",
                            "content": [{
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{img_base64}"}
                            }, {
                                "type": "text",
                                "text": self._get_prompt()
                            }]
                        }]
                    },
                    headers={"Authorization": f"Bearer {self.gpt4o_api_key}", "Content-Type": "application/json"}
                ),
                timeout=self.timeout
            )
            
            result_text = response.json()["choices"][0]["message"]["content"]
            return self._parse_response(result_text, VisionMode.CLOUD_GPT4O)
        except asyncio.TimeoutError:
            logger.warning("GPT-4o timeout")
            return None
        except Exception as e:
            logger.error(f"GPT-4o failed: {e}")
            return None
    
    async def _analyze_with_deepseek(self, screenshot: Image.Image) -> Optional[ScreenAnalysisResult]:
        """DeepSeek 分析"""
        try:
            if not HAS_HTTPX or not self.http_client:
                return None
            
            img_bytes = io.BytesIO()
            screenshot.save(img_bytes, format='PNG')
            img_base64 = base64.b64encode(img_bytes.getvalue()).decode()
            
            response = await asyncio.wait_for(
                self.http_client.post(
                    "https://api.deepseek.com/chat/completions",
                    json={
                        "model": "deepseek-vision",
                        "messages": [{
                            "role": "user",
                            "content": [{
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{img_base64}"}
                            }, {
                                "type": "text",
                                "text": self._get_prompt()
                            }]
                        }]
                    },
                    headers={"Authorization": f"Bearer {self.deepseek_api_key}", "Content-Type": "application/json"}
                ),
                timeout=self.timeout
            )
            
            result_text = response.json()["choices"][0]["message"]["content"]
            return self._parse_response(result_text, VisionMode.CLOUD_DEEPSEEK)
        except asyncio.TimeoutError:
            logger.warning("DeepSeek timeout")
            return None
        except Exception as e:
            logger.error(f"DeepSeek failed: {e}")
            return None
    
    async def _fallback_ocr_analysis(self, screenshot: Optional[Image.Image] = None) -> ScreenAnalysisResult:
        """OCR 降级"""
        try:
            logger.info("Falling back to OCR...")
            
            if screenshot is None:
                screenshot = await self._take_screenshot()
            
            if screenshot is None or self.ocr is None:
                return ScreenAnalysisResult(None, None, None, VisionMode.FALLBACK_OCR, "OCR unavailable", time.time())
            
            results = self.ocr.readtext(np.array(screenshot))
            
            latest_message = None
            send_button_pos = None
            
            for (bbox, text, confidence) in results:
                if "发送" in text or "send" in text.lower():
                    x = int((bbox[0][0] + bbox[2][0]) / 2)
                    y = int((bbox[0][1] + bbox[2][1]) / 2)
                    send_button_pos = (x, y)
                elif confidence > 0.5:
                    latest_message = text
            
            input_box_pos = (screenshot.width // 2, int(screenshot.height * 0.9)) if screenshot else None
            
            return ScreenAnalysisResult(latest_message, input_box_pos, send_button_pos, VisionMode.FALLBACK_OCR, f"OCR: {len(results)} regions", time.time())
        except Exception as e:
            logger.error(f"OCR failed: {e}")
            return ScreenAnalysisResult(None, None, None, VisionMode.FALLBACK_OCR, f"Error: {str(e)}", time.time())
    
    def _get_prompt(self) -> str:
        return """分析微信截图，返回 JSON：
{"latest_message":"最新消息","input_box":{"x":x,"y":y},"send_button":{"x":x,"y":y},"confidence":0.0}"""
    
    def _parse_response(self, response_text: str, mode: VisionMode) -> Optional[ScreenAnalysisResult]:
        """解析响应"""
        try:
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            
            if json_start == -1 or json_end == 0:
                return None
            
            data = json.loads(response_text[json_start:json_end])
            
            input_box_pos = (data["input_box"]["x"], data["input_box"]["y"]) if data.get("input_box") else None
            send_button_pos = (data["send_button"]["x"], data["send_button"]["y"]) if data.get("send_button") else None
            
            return ScreenAnalysisResult(data.get("latest_message"), input_box_pos, send_button_pos, mode, response_text, time.time())
        except Exception as e:
            logger.error(f"Parse failed: {e}")
            return None
    
    async def click_with_bezier(self, x: int, y: int, duration: float = 0.5):
        """贝塞尔曲线点击"""
        if self.device is None:
            return False
        
        try:
            self.device.touch(x, y, duration=duration)
            logger.info(f"Clicked at ({x}, {y})")
            return True
        except Exception as e:
            logger.error(f"Click failed: {e}")
            return False
    
    async def close(self):
        """关闭"""
        if self.http_client:
            await self.http_client.aclose()

_analyzer: Optional[OmniVisionAnalyzer] = None

async def get_analyzer() -> OmniVisionAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = OmniVisionAnalyzer()
    return _analyzer

async def analyze_screen() -> ScreenAnalysisResult:
    analyzer = await get_analyzer()
    return await analyzer.analyze_screen()

async def click_at(x: int, y: int):
    analyzer = await get_analyzer()
    return await analyzer.click_with_bezier(x, y)
