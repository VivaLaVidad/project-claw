"""
hardware_override.py - 极简硬件干预接口
支持商户通过智能手表/按钮发送 ACCEPT 或 REJECT 指令
能瞬间打断 LangGraph 运行并接管最终输出
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, Callable, Any
import asyncio
import threading
from enum import Enum
from datetime import datetime
import json


class OverrideCommand(str, Enum):
    """硬件干预命令"""
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    PAUSE = "PAUSE"
    RESUME = "RESUME"


class OverrideRequest(BaseModel):
    """硬件干预请求"""
    merchant_id: str
    command: OverrideCommand
    reason: Optional[str] = None
    timestamp: Optional[float] = None


class OverrideResponse(BaseModel):
    """硬件干预响应"""
    success: bool
    message: str
    command: OverrideCommand
    executed_at: float


class HardwareOverrideManager:
    """硬件干预管理器"""
    
    def __init__(self):
        """初始化硬件干预管理器"""
        self.current_negotiation: Optional[dict] = None
        self.override_event = asyncio.Event()
        self.override_command: Optional[OverrideCommand] = None
        self.override_callbacks: dict[OverrideCommand, Callable] = {}
        self.lock = threading.RLock()
    
    def register_override_callback(
        self,
        command: OverrideCommand,
        callback: Callable[[dict], Any]
    ):
        """
        注册硬件干预回调
        
        Args:
            command: 命令类型
            callback: 回调函数
        """
        self.override_callbacks[command] = callback
    
    async def set_current_negotiation(self, negotiation_data: dict):
        """设置当前谈判上下文"""
        with self.lock:
            self.current_negotiation = negotiation_data
            self.override_event.clear()
    
    async def wait_for_override(self, timeout: float = 300) -> Optional[OverrideCommand]:
        """
        等待硬件干预命令
        
        Args:
            timeout: 超时时间（秒）
        
        Returns:
            OverrideCommand 或 None（超时）
        """
        try:
            await asyncio.wait_for(self.override_event.wait(), timeout=timeout)
            return self.override_command
        except asyncio.TimeoutError:
            return None
    
    async def process_override(self, request: OverrideRequest) -> OverrideResponse:
        """
        处理硬件干预请求
        
        Args:
            request: 硬件干预请求
        
        Returns:
            硬件干预响应
        """
        with self.lock:
            # 验证商家
            if not self.current_negotiation:
                raise HTTPException(
                    status_code=400,
                    detail="No active negotiation"
                )
            
            if self.current_negotiation.get('merchant_id') != request.merchant_id:
                raise HTTPException(
                    status_code=403,
                    detail="Merchant ID mismatch"
                )
            
            # 设置覆盖命令
            self.override_command = request.command
            self.override_event.set()
            
            # 执行回调
            if request.command in self.override_callbacks:
                callback = self.override_callbacks[request.command]
                try:
                    await callback(self.current_negotiation)
                except Exception as e:
                    print(f"Error executing override callback: {e}")
            
            return OverrideResponse(
                success=True,
                message=f"Override command {request.command} executed",
                command=request.command,
                executed_at=datetime.now().timestamp(),
            )
    
    def get_current_state(self) -> dict:
        """获取当前状态"""
        with self.lock:
            return {
                'has_active_negotiation': self.current_negotiation is not None,
                'current_negotiation': self.current_negotiation,
                'last_override': self.override_command,
            }


# 全局硬件干预管理器
_override_manager: Optional[HardwareOverrideManager] = None


def get_override_manager() -> HardwareOverrideManager:
    """获取全局硬件干预管理器"""
    global _override_manager
    if _override_manager is None:
        _override_manager = HardwareOverrideManager()
    return _override_manager


def create_override_api(app: FastAPI):
    """
    为 FastAPI 应用创建硬件干预 API
    
    Args:
        app: FastAPI 应用实例
    """
    manager = get_override_manager()
    
    @app.post("/api/v1/override", response_model=OverrideResponse)
    async def handle_override(request: OverrideRequest):
        """
        硬件干预端点
        
        支持商户通过智能手表/按钮发送命令
        
        Example:
            POST /api/v1/override
            {
                "merchant_id": "box-001",
                "command": "ACCEPT",
                "reason": "Customer confirmed via smartwatch"
            }
        """
        return await manager.process_override(request)
    
    @app.get("/api/v1/override/status")
    async def get_override_status():
        """获取硬件干预状态"""
        return manager.get_current_state()
    
    return manager


# 集成到 LangGraph 的中断机制
class LangGraphInterruptor:
    """LangGraph 中断器 - 支持硬件干预"""
    
    def __init__(self, override_manager: HardwareOverrideManager):
        """
        初始化 LangGraph 中断器
        
        Args:
            override_manager: 硬件干预管理器
        """
        self.override_manager = override_manager
    
    async def should_interrupt(self) -> bool:
        """检查是否应该中断"""
        # 检查是否有待处理的覆盖命令
        if self.override_manager.override_event.is_set():
            return True
        return False
    
    async def get_interrupt_action(self) -> Optional[OverrideCommand]:
        """获取中断动作"""
        if self.override_manager.override_event.is_set():
            return self.override_manager.override_command
        return None
    
    async def handle_interrupt(self, command: OverrideCommand) -> dict:
        """
        处理中断
        
        Args:
            command: 中断命令
        
        Returns:
            中断处理结果
        """
        if command == OverrideCommand.ACCEPT:
            return await self._handle_accept()
        elif command == OverrideCommand.REJECT:
            return await self._handle_reject()
        elif command == OverrideCommand.PAUSE:
            return await self._handle_pause()
        elif command == OverrideCommand.RESUME:
            return await self._handle_resume()
    
    async def _handle_accept(self) -> dict:
        """处理接受命令"""
        negotiation = self.override_manager.current_negotiation
        return {
            'status': 'ACCEPTED',
            'reason': 'Hardware override - ACCEPT',
            'negotiation_id': negotiation.get('intent_id'),
            'timestamp': datetime.now().timestamp(),
        }
    
    async def _handle_reject(self) -> dict:
        """处理拒绝命令"""
        negotiation = self.override_manager.current_negotiation
        return {
            'status': 'REJECTED',
            'reason': 'Hardware override - REJECT',
            'negotiation_id': negotiation.get('intent_id'),
            'timestamp': datetime.now().timestamp(),
        }
    
    async def _handle_pause(self) -> dict:
        """处理暂停命令"""
        return {
            'status': 'PAUSED',
            'reason': 'Hardware override - PAUSE',
            'timestamp': datetime.now().timestamp(),
        }
    
    async def _handle_resume(self) -> dict:
        """处理恢复命令"""
        return {
            'status': 'RESUMED',
            'reason': 'Hardware override - RESUME',
            'timestamp': datetime.now().timestamp(),
        }
