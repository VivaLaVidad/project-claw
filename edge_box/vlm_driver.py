"""Project Claw VLM 物理执行驱动层 - edge_box/vlm_driver.py"""
import asyncio, logging, json, base64, re
from typing import Dict, Optional, Any
from dataclasses import dataclass
from enum import Enum
import httpx
import subprocess

logger = logging.getLogger(__name__)

class UIElementType(str, Enum):
    BUTTON = "button"
    INPUT = "input"
    TEXT = "text"
    MESSAGE = "message"

@dataclass
class UIElement:
    element_type: UIElementType
    description: str
    center_x: int
    center_y: int
    confidence: float

@dataclass
class VLMConfig:
    api_key: str
    model: str = "gpt-4-vision"
    base_url: str = "https://api.openai.com/v1"
    timeout: float = 30.0

class VLMParser:
    """VLM 响应解析器"""
    
    @staticmethod
    def parse_response(response_text: str) -> Optional[Dict[str, Any]]:
        """解析 VLM 响应为 JSON"""
        try:
            if response_text.strip().startswith("{"):
                return json.loads(response_text)
            
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(1))
            
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
            
            logger.warning(f"无法解析 VLM 响应: {response_text[:100]}")
            return None
        except Exception as e:
            logger.error(f"解析响应失败: {e}")
            return None

class VLMDriver:
    """VLM 物理执行驱动"""
    
    def __init__(self, config: VLMConfig):
        self.config = config
        self.client = httpx.AsyncClient(timeout=config.timeout)
        self.parser = VLMParser()
    
    async def find_ui_element(
        self,
        screenshot_base64: str,
        instruction: str,
        fallback_ocr_func: Optional[callable] = None
    ) -> Optional[UIElement]:
        """使用 VLM 查找 UI 元素"""
        
        try:
            logger.info(f"调用 VLM 查找元素: {instruction}")
            
            response_text = await self._call_vlm(screenshot_base64, instruction)
            
            if not response_text:
                logger.warning("VLM 返回空响应")
                return await self._fallback_to_ocr(instruction, fallback_ocr_func)
            
            parsed = self.parser.parse_response(response_text)
            
            if not parsed:
                logger.warning("VLM 响应解析失败")
                return await self._fallback_to_ocr(instruction, fallback_ocr_func)
            
            if "found" in parsed and not parsed["found"]:
                logger.warning(f"VLM 未找到元素: {parsed.get('reason', 'unknown')}")
                return await self._fallback_to_ocr(instruction, fallback_ocr_func)
            
            element = UIElement(
                element_type=UIElementType(parsed.get("element_type", "button")),
                description=parsed.get("description", instruction),
                center_x=int(parsed.get("center_x", 0)),
                center_y=int(parsed.get("center_y", 0)),
                confidence=float(parsed.get("confidence", 0.8))
            )
            
            logger.info(f"✓ VLM 找到元素: ({element.center_x}, {element.center_y}) 置信度: {element.confidence}")
            return element
        
        except Exception as e:
            logger.error(f"VLM 查找失败: {e}")
            return await self._fallback_to_ocr(instruction, fallback_ocr_func)
    
    async def _call_vlm(self, screenshot_base64: str, instruction: str) -> Optional[str]:
        """调用 VLM API"""
        
        try:
            system_prompt = """你是一个 UI 自动化专家。分析手机截图，找出指定的 UI 元素。

返回 JSON 格式：
{
    "found": true/false,
    "element_type": "button|input|text|message",
    "description": "元素描述",
    "center_x": X坐标,
    "center_y": Y坐标,
    "confidence": 置信度(0-1),
    "reason": "未找到时的原因"
}

规则：
1. 坐标范围: X(0-1080), Y(0-1920)
2. 必须返回有效 JSON
3. 置信度反映确定程度"""
            
            headers = {
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": self.config.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{screenshot_base64}"}},
                            {"type": "text", "text": instruction}
                        ]
                    }
                ],
                "max_tokens": 500
            }
            
            response = await self.client.post(
                f"{self.config.base_url}/chat/completions",
                headers=headers,
                json=payload
            )
            
            if response.status_code == 200:
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                logger.info(f"VLM 响应: {content[:100]}")
                return content
            else:
                logger.error(f"VLM API 错误: {response.status_code}")
                return None
        
        except Exception as e:
            logger.error(f"调用 VLM 失败: {e}")
            return None
    
    async def _fallback_to_ocr(
        self,
        instruction: str,
        fallback_ocr_func: Optional[callable]
    ) -> Optional[UIElement]:
        """降级到 OCR 搜索"""
        
        try:
            if not fallback_ocr_func:
                logger.warning("没有提供 OCR 降级函数")
                return None
            
            logger.info(f"降级到 OCR 搜索: {instruction}")
            
            result = await fallback_ocr_func(instruction)
            
            if result:
                logger.info(f"✓ OCR 找到元素: {result}")
                return UIElement(
                    element_type=UIElementType.BUTTON,
                    description=instruction,
                    center_x=result.get("x", 0),
                    center_y=result.get("y", 0),
                    confidence=0.6
                )
            
            logger.warning("OCR 也未找到元素")
            return None
        
        except Exception as e:
            logger.error(f"OCR 降级失败: {e}")
            return None
    
    async def close(self):
        """关闭客户端"""
        await self.client.aclose()
        logger.info("✓ VLM 驱动已关闭")

class PhysicalExecutor:
    """物理执行器 - 基于 VLM 的 UI 操控"""
    
    def __init__(self, vlm_driver: VLMDriver, device_id: Optional[str] = None):
        self.vlm_driver = vlm_driver
        self.device_id = device_id or self._get_device_id()
    
    def _get_device_id(self) -> str:
        """获取设备 ID"""
        try:
            result = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=5)
            lines = result.stdout.strip().split("\n")
            if len(lines) > 1:
                device_id = lines[1].split()[0]
                logger.info(f"检测到设备: {device_id}")
                return device_id
        except Exception as e:
            logger.error(f"获取设备 ID 失败: {e}")
        return "emulator-5554"
    
    async def tap_element(
        self,
        screenshot_base64: str,
        instruction: str,
        fallback_ocr_func: Optional[callable] = None
    ) -> bool:
        """点击 UI 元素"""
        
        try:
            element = await self.vlm_driver.find_ui_element(
                screenshot_base64,
                instruction,
                fallback_ocr_func
            )
            
            if not element:
                logger.error(f"无法找到元素: {instruction}")
                return False
            
            logger.info(f"点击元素: ({element.center_x}, {element.center_y})")
            return await self._execute_tap(element.center_x, element.center_y)
        
        except Exception as e:
            logger.error(f"点击元素失败: {e}")
            return False
    
    async def _execute_tap(self, x: int, y: int) -> bool:
        """执行点击操作"""
        
        try:
            cmd = f"adb -s {self.device_id} shell input tap {x} {y}"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
            
            if result.returncode == 0:
                logger.info(f"✓ 点击成功: ({x}, {y})")
                return True
            else:
                logger.error(f"点击失败: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"执行点击失败: {e}")
            return False
    
    async def type_text(
        self,
        screenshot_base64: str,
        instruction: str,
        text: str,
        fallback_ocr_func: Optional[callable] = None
    ) -> bool:
        """在输入框中输入文本"""
        
        try:
            success = await self.tap_element(screenshot_base64, instruction, fallback_ocr_func)
            
            if not success:
                logger.error("无法点击输入框")
                return False
            
            await asyncio.sleep(0.5)
            
            cmd = f"adb -s {self.device_id} shell input text '{text}'"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
            
            if result.returncode == 0:
                logger.info(f"✓ 输入成功: {text}")
                return True
            else:
                logger.error(f"输入失败: {result.stderr}")
                return False
        
        except Exception as e:
            logger.error(f"输入文本失败: {e}")
            return False
    
    async def swipe(self, start_x: int, start_y: int, end_x: int, end_y: int, duration: int = 500) -> bool:
        """滑动操作"""
        
        try:
            cmd = f"adb -s {self.device_id} shell input swipe {start_x} {start_y} {end_x} {end_y} {duration}"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
            
            if result.returncode == 0:
                logger.info(f"✓ 滑动成功: ({start_x}, {start_y}) -> ({end_x}, {end_y})")
                return True
            else:
                logger.error(f"滑动失败: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"滑动操作失败: {e}")
            return False
    
    async def get_screenshot(self) -> Optional[str]:
        """获取截图并转换为 base64"""
        
        try:
            cmd = f"adb -s {self.device_id} shell screencap -p /sdcard/screenshot.png"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
            
            if result.returncode != 0:
                logger.error(f"获取截图失败: {result.stderr}")
                return None
            
            cmd = f"adb -s {self.device_id} pull /sdcard/screenshot.png /tmp/screenshot.png"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
            
            if result.returncode != 0:
                logger.error(f"拉取截图失败: {result.stderr}")
                return None
            
            with open("/tmp/screenshot.png", "rb") as f:
                screenshot_base64 = base64.b64encode(f.read()).decode()
            
            logger.info("✓ 截图获取成功")
            return screenshot_base64
        
        except Exception as e:
            logger.error(f"获取截图失败: {e}")
            return None
