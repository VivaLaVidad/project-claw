"""
Project Claw GUI Agent 执行器与完整系统
文件位置：edge_box/gui_agent_executor.py
"""

import asyncio
import logging
from typing import Dict, List, Any
from abc import ABC, abstractmethod

from .visual_action_driver import (
    VisualActionDriver, VLMDriver, VisualAction, ActionType
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# 第 1 部分：操作执行器
# ═══════════════════════════════════════════════════════════════

class ActionExecutor(ABC):
    """操作执行器基类"""
    
    @abstractmethod
    async def execute(self, action: VisualAction) -> bool:
        """执行操作"""
        pass


class AndroidActionExecutor(ActionExecutor):
    """Android 操作执行器"""
    
    def __init__(self, device_id: str = None):
        self.device_id = device_id
    
    async def execute(self, action: VisualAction) -> bool:
        """执行操作"""
        
        try:
            if action.action_type == ActionType.CLICK:
                return await self._click(action)
            elif action.action_type == ActionType.DOUBLE_CLICK:
                return await self._double_click(action)
            elif action.action_type == ActionType.LONG_PRESS:
                return await self._long_press(action)
            elif action.action_type == ActionType.SWIPE:
                return await self._swipe(action)
            elif action.action_type == ActionType.TYPE:
                return await self._type(action)
            elif action.action_type == ActionType.SCROLL:
                return await self._scroll(action)
            elif action.action_type == ActionType.WAIT:
                return await self._wait(action)
            elif action.action_type == ActionType.BACK:
                return await self._back()
            elif action.action_type == ActionType.HOME:
                return await self._home()
            else:
                logger.warning(f"未知的操作类型: {action.action_type}")
                return False
        
        except Exception as e:
            logger.error(f"执行操作失败: {e}")
            return False
    
    async def _click(self, action: VisualAction) -> bool:
        """点击"""
        if not action.target_bbox:
            return False
        
        x, y = action.target_bbox.center
        logger.info(f"点击: ({x:.2f}, {y:.2f})")
        # 实际实现：使用 adb 或 uiautomator2
        # subprocess.run(['adb', 'shell', 'input', 'tap', str(int(x)), str(int(y))])
        return True
    
    async def _double_click(self, action: VisualAction) -> bool:
        """双击"""
        if not action.target_bbox:
            return False
        
        x, y = action.target_bbox.center
        logger.info(f"双击: ({x:.2f}, {y:.2f})")
        return True
    
    async def _long_press(self, action: VisualAction) -> bool:
        """长按"""
        if not action.target_bbox:
            return False
        
        x, y = action.target_bbox.center
        logger.info(f"长按: ({x:.2f}, {y:.2f})")
        return True
    
    async def _swipe(self, action: VisualAction) -> bool:
        """滑动"""
        direction = action.swipe_direction or "up"
        distance = action.swipe_distance
        logger.info(f"滑动: {direction} ({distance:.2f})")
        return True
    
    async def _type(self, action: VisualAction) -> bool:
        """输入文本"""
        text = action.text_input or ""
        logger.info(f"输入: {text}")
        return True
    
    async def _scroll(self, action: VisualAction) -> bool:
        """滚动"""
        logger.info("滚动")
        return True
    
    async def _wait(self, action: VisualAction) -> bool:
        """等待"""
        wait_time = action.wait_time
        logger.info(f"等待: {wait_time}秒")
        await asyncio.sleep(wait_time)
        return True
    
    async def _back(self) -> bool:
        """返回"""
        logger.info("返回")
        return True
    
    async def _home(self) -> bool:
        """主页"""
        logger.info("主页")
        return True


# ═══════════════════════════════════════════════════════════════
# 第 2 部分：完整的 GUI Agent 系统
# ═══════════════════════════════════════════════════════════════

class GUIAgent:
    """GUI Agent - 完整的视觉操作系统"""
    
    def __init__(
        self,
        vlm_driver: VLMDriver,
        action_executor: ActionExecutor,
        screen_width: int = 1080,
        screen_height: int = 1920
    ):
        self.visual_driver = VisualActionDriver(
            vlm_driver,
            screen_width,
            screen_height
        )
        self.action_executor = action_executor
        self.screen_width = screen_width
        self.screen_height = screen_height
    
    async def execute_task(
        self,
        screenshot_base64: str,
        task_description: str,
        steps: List[str]
    ) -> Dict[str, Any]:
        """
        执行任务
        
        Args:
            screenshot_base64: 截图的 base64 编码
            task_description: 任务描述
            steps: 步骤列表
        
        Returns:
            执行结果
        """
        
        logger.info(f"执行任务: {task_description}")
        logger.info(f"步骤数: {len(steps)}")
        
        results = []
        
        for i, step in enumerate(steps, 1):
            logger.info(f"\n第 {i}/{len(steps)} 步: {step}")
            
            # 生成操作
            success, action, message = await self.visual_driver.execute_instruction(
                screenshot_base64,
                step
            )
            
            if not success:
                logger.error(f"步骤失败: {message}")
                results.append({
                    "step": step,
                    "success": False,
                    "message": message
                })
                break
            
            # 执行操作
            exec_success = await self.action_executor.execute(action)
            
            results.append({
                "step": step,
                "success": exec_success,
                "action": action.action_type.value,
                "confidence": action.confidence,
                "reasoning": action.reasoning
            })
            
            if not exec_success:
                logger.error(f"操作执行失败")
                break
            
            # 等待
            await asyncio.sleep(1.0)
        
        return {
            "task": task_description,
            "total_steps": len(steps),
            "completed_steps": len([r for r in results if r["success"]]),
            "results": results,
            "action_history": self.visual_driver.get_action_history(),
            "ui_elements": self.visual_driver.get_ui_elements()
        }
    
    async def execute_single_instruction(
        self,
        screenshot_base64: str,
        instruction: str
    ) -> Dict[str, Any]:
        """
        执行单个指令
        
        Args:
            screenshot_base64: 截图的 base64 编码
            instruction: 指令（例如 "点击转账按钮"）
        
        Returns:
            执行结果
        """
        
        logger.info(f"执行指令: {instruction}")
        
        success, action, message = await self.visual_driver.execute_instruction(
            screenshot_base64,
            instruction
        )
        
        if not success:
            return {
                "success": False,
                "message": message,
                "action": None
            }
        
        # 执行操作
        exec_success = await self.action_executor.execute(action)
        
        return {
            "success": exec_success,
            "message": "操作执行成功" if exec_success else "操作执行失败",
            "action": {
                "type": action.action_type.value,
                "confidence": action.confidence,
                "reasoning": action.reasoning,
                "target_element": action.target_element.element_id if action.target_element else None
            }
        }
    
    def get_execution_report(self) -> Dict[str, Any]:
        """获取执行报告"""
        return {
            "action_history": self.visual_driver.get_action_history(),
            "ui_elements": self.visual_driver.get_ui_elements(),
            "total_actions": len(self.visual_driver.action_history),
            "avg_confidence": (
                sum(a.confidence for a in self.visual_driver.action_history) / 
                len(self.visual_driver.action_history)
                if self.visual_driver.action_history else 0
            )
        }


# ═══════════════════════════════════════════════════════════════
# 第 3 部分：使用示例
# ═══════════════════════════════════════════════════════════════

async def example_usage():
    """使用示例"""
    
    from .visual_action_driver import LocalVLMDriver
    
    # 初始化 VLM 驱动
    vlm_driver = LocalVLMDriver(api_key="your-api-key")
    
    # 初始化操作执行器
    executor = AndroidActionExecutor(device_id="device-001")
    
    # 创建 GUI Agent
    agent = GUIAgent(
        vlm_driver=vlm_driver,
        action_executor=executor,
        screen_width=1080,
        screen_height=1920
    )
    
    # 执行任务
    result = await agent.execute_task(
        screenshot_base64="base64_encoded_screenshot",
        task_description="完成转账操作",
        steps=[
            "点击转账按钮",
            "输入收款人账号",
            "输入转账金额",
            "点击确认按钮"
        ]
    )
    
    print(result)
    
    # 获取执行报告
    report = agent.get_execution_report()
    print(report)
