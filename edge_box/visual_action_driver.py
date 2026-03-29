"""
Project Claw 视觉 GUI Agent 驱动层 - 数据模型与 VLM 驱动
基于 UI-TARS/Ferret-UI 的最新实现机制
文件位置：edge_box/visual_action_driver.py
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
from abc import ABC, abstractmethod
import httpx

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# 第 1 部分：数据模型定义
# ═══════════════════════════════════════════════════════════════

class ActionType(str, Enum):
    """操作类型"""
    CLICK = "click"
    DOUBLE_CLICK = "double_click"
    LONG_PRESS = "long_press"
    SWIPE = "swipe"
    TYPE = "type"
    SCROLL = "scroll"
    WAIT = "wait"
    BACK = "back"
    HOME = "home"


@dataclass
class BoundingBox:
    """归一化边界框 (0-1 范围)"""
    x1: float
    y1: float
    x2: float
    y2: float
    
    @property
    def center(self) -> Tuple[float, float]:
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)
    
    @property
    def width(self) -> float:
        return self.x2 - self.x1
    
    @property
    def height(self) -> float:
        return self.y2 - self.y1
    
    def to_pixel_coords(self, screen_width: int, screen_height: int) -> Tuple[int, int]:
        cx, cy = self.center
        return (int(cx * screen_width), int(cy * screen_height))


@dataclass
class UIElement:
    """UI 元素"""
    element_id: str
    text: str
    bbox: BoundingBox
    element_type: str
    confidence: float
    description: str = ""


@dataclass
class VisualAction:
    """视觉操作"""
    action_type: ActionType
    target_element: Optional[UIElement] = None
    target_bbox: Optional[BoundingBox] = None
    text_input: Optional[str] = None
    swipe_direction: Optional[str] = None
    swipe_distance: float = 0.3
    wait_time: float = 1.0
    confidence: float = 1.0
    reasoning: str = ""


# ═══════════════════════════════════════════════════════════════
# 第 2 部分：VLM 驱动层
# ═══════════════════════════════════════════════════════════════

class VLMDriver(ABC):
    """VLM 驱动基类"""
    
    @abstractmethod
    async def extract_ui_elements(
        self,
        image_base64: str,
        screen_width: int,
        screen_height: int
    ) -> List[UIElement]:
        pass
    
    @abstractmethod
    async def generate_action(
        self,
        image_base64: str,
        ui_elements: List[UIElement],
        instruction: str,
        screen_width: int,
        screen_height: int
    ) -> VisualAction:
        pass


class LocalVLMDriver(VLMDriver):
    """本地 VLM 驱动 - 使用 DeepSeek/Claude 等 API"""
    
    def __init__(self, api_key: str, model: str = "deepseek-vision"):
        self.api_key = api_key
        self.model = model
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def extract_ui_elements(
        self,
        image_base64: str,
        screen_width: int,
        screen_height: int
    ) -> List[UIElement]:
        """提取 UI 元素"""
        prompt = """
        分析这个手机屏幕截图，识别所有可交互的 UI 元素。
        
        返回 JSON 格式：
        {
            "elements": [
                {
                    "id": "element_1",
                    "text": "按钮文本",
                    "bbox": {"x1": 0.1, "y1": 0.2, "x2": 0.9, "y2": 0.3},
                    "type": "button",
                    "confidence": 0.95,
                    "description": "转账按钮"
                }
            ]
        }
        """
        
        try:
            response = await self.client.post(
                "https://api.deepseek.com/v1/vision/analyze",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "image": image_base64,
                    "prompt": prompt,
                    "max_tokens": 2000
                }
            )
            
            result = response.json()
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "{}")
            data = json.loads(content)
            elements = []
            
            for elem_data in data.get("elements", []):
                bbox_data = elem_data.get("bbox", {})
                bbox = BoundingBox(
                    x1=bbox_data.get("x1", 0),
                    y1=bbox_data.get("y1", 0),
                    x2=bbox_data.get("x2", 1),
                    y2=bbox_data.get("y2", 1)
                )
                
                element = UIElement(
                    element_id=elem_data.get("id", ""),
                    text=elem_data.get("text", ""),
                    bbox=bbox,
                    element_type=elem_data.get("type", "unknown"),
                    confidence=elem_data.get("confidence", 0.5),
                    description=elem_data.get("description", "")
                )
                elements.append(element)
            
            logger.info(f"提取 {len(elements)} 个 UI 元素")
            return elements
            
        except Exception as e:
            logger.error(f"提取 UI 元素失败: {e}")
            return []
    
    async def generate_action(
        self,
        image_base64: str,
        ui_elements: List[UIElement],
        instruction: str,
        screen_width: int,
        screen_height: int
    ) -> VisualAction:
        """生成操作"""
        
        elements_desc = "\n".join([
            f"- [{elem.element_id}] {elem.element_type}: '{elem.text}' "
            f"({elem.description}) bbox={elem.bbox.__dict__}"
            for elem in ui_elements
        ])
        
        prompt = f"""
        根据用户指令和当前屏幕，生成一个操作。
        
        用户指令：{instruction}
        
        可用的 UI 元素：
        {elements_desc}
        
        返回 JSON 格式：
        {{
            "action_type": "click|swipe|type|wait",
            "target_element_id": "element_id 或 null",
            "target_bbox": {{"x1": 0.1, "y1": 0.2, "x2": 0.9, "y2": 0.3}} 或 null,
            "text_input": "输入的文本 或 null",
            "swipe_direction": "up|down|left|right 或 null",
            "confidence": 0.95,
            "reasoning": "为什么选择这个操作"
        }}
        """
        
        try:
            response = await self.client.post(
                "https://api.deepseek.com/v1/vision/analyze",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "image": image_base64,
                    "prompt": prompt,
                    "max_tokens": 1000
                }
            )
            
            result = response.json()
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "{}")
            action_data = json.loads(content)
            
            target_element = None
            if action_data.get("target_element_id"):
                target_element = next(
                    (e for e in ui_elements if e.element_id == action_data["target_element_id"]),
                    None
                )
            
            target_bbox = None
            if action_data.get("target_bbox"):
                bbox_data = action_data["target_bbox"]
                target_bbox = BoundingBox(
                    x1=bbox_data.get("x1", 0),
                    y1=bbox_data.get("y1", 0),
                    x2=bbox_data.get("x2", 1),
                    y2=bbox_data.get("y2", 1)
                )
            elif target_element:
                target_bbox = target_element.bbox
            
            action = VisualAction(
                action_type=ActionType(action_data.get("action_type", "click")),
                target_element=target_element,
                target_bbox=target_bbox,
                text_input=action_data.get("text_input"),
                swipe_direction=action_data.get("swipe_direction"),
                swipe_distance=action_data.get("swipe_distance", 0.3),
                wait_time=action_data.get("wait_time", 1.0),
                confidence=action_data.get("confidence", 0.5),
                reasoning=action_data.get("reasoning", "")
            )
            
            logger.info(f"生成操作: {action.action_type.value} (置信度: {action.confidence})")
            return action
            
        except Exception as e:
            logger.error(f"生成操作失败: {e}")
            return VisualAction(
                action_type=ActionType.WAIT,
                wait_time=1.0,
                confidence=0.0,
                reasoning=f"错误: {str(e)}"
            )


# ═══════════════════════════════════════════════════════════════
# 第 3 部分：VisualActionDriver - 主驱动类
# ═══════════════════════════════════════════════════════════════

class VisualActionDriver:
    """视觉操作驱动 - 基于 VLM 的 GUI Agent"""
    
    def __init__(
        self,
        vlm_driver: VLMDriver,
        screen_width: int = 1080,
        screen_height: int = 1920
    ):
        self.vlm_driver = vlm_driver
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.ui_elements_cache: List[UIElement] = []
        self.action_history: List[VisualAction] = []
    
    async def execute_instruction(
        self,
        screenshot_base64: str,
        instruction: str
    ) -> Tuple[bool, VisualAction, str]:
        """执行指令"""
        
        logger.info(f"执行指令: {instruction}")
        
        try:
            # 提取 UI 元素
            logger.info("提取 UI 元素...")
            ui_elements = await self.vlm_driver.extract_ui_elements(
                screenshot_base64,
                self.screen_width,
                self.screen_height
            )
            self.ui_elements_cache = ui_elements
            
            if not ui_elements:
                return False, None, "无法识别 UI 元素"
            
            # 生成操作
            logger.info("生成操作...")
            action = await self.vlm_driver.generate_action(
                screenshot_base64,
                ui_elements,
                instruction,
                self.screen_width,
                self.screen_height
            )
            
            # 验证置信度
            if action.confidence < 0.5:
                logger.warning(f"操作置信度过低: {action.confidence}")
                return False, action, f"操作置信度过低: {action.confidence}"
            
            # 记录操作
            self.action_history.append(action)
            
            logger.info(f"✓ 操作生成成功: {action.action_type.value}")
            return True, action, "操作生成成功"
            
        except Exception as e:
            logger.error(f"执行指令失败: {e}")
            return False, None, f"错误: {str(e)}"
    
    def get_action_history(self) -> List[Dict]:
        """获取操作历史"""
        return [
            {
                "action_type": action.action_type.value,
                "target_element": action.target_element.element_id if action.target_element else None,
                "text_input": action.text_input,
                "confidence": action.confidence,
                "reasoning": action.reasoning
            }
            for action in self.action_history
        ]
    
    def get_ui_elements(self) -> List[Dict]:
        """获取 UI 元素"""
        return [
            {
                "id": elem.element_id,
                "text": elem.text,
                "type": elem.element_type,
                "bbox": elem.bbox.__dict__,
                "confidence": elem.confidence,
                "description": elem.description
            }
            for elem in self.ui_elements_cache
        ]
