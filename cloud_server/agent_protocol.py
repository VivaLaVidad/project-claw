"""
Project Claw Agent通信系统 - 第1部分：协议与基类
文件位置：cloud_server/agent_protocol.py
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# 通信协议定义
# ═══════════════════════════════════════════════════════════════

class MessageType(str, Enum):
    """消息类型"""
    INQUIRY = "INQUIRY"              # C端询价
    OFFER = "OFFER"                  # B端报价
    COUNTER_OFFER = "COUNTER_OFFER"  # C端反价
    ACCEPTANCE = "ACCEPTANCE"        # 接受
    REJECTION = "REJECTION"          # 拒绝
    NEGOTIATION = "NEGOTIATION"      # 谈判
    FINAL_DECISION = "FINAL_DECISION" # 最终决定


class AgentRole(str, Enum):
    """Agent角色"""
    CLIENT_AGENT = "CLIENT_AGENT"      # C端Agent
    MERCHANT_AGENT = "MERCHANT_AGENT"  # B端Agent
    ORCHESTRATOR = "ORCHESTRATOR"      # 协调器


class NegotiationStatus(str, Enum):
    """谈判状态"""
    INITIATED = "INITIATED"            # 已启动
    IN_PROGRESS = "IN_PROGRESS"        # 进行中
    AGREEMENT_REACHED = "AGREEMENT_REACHED"  # 达成协议
    FAILED = "FAILED"                  # 失败
    TIMEOUT = "TIMEOUT"                # 超时


@dataclass
class AgentMessage:
    """Agent消息"""
    message_id: str
    session_id: str
    sender_role: AgentRole
    sender_id: str
    receiver_role: AgentRole
    receiver_id: str
    message_type: MessageType
    content: Dict[str, Any]
    timestamp: float
    round_number: int
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "message_id": self.message_id,
            "session_id": self.session_id,
            "sender_role": self.sender_role.value,
            "sender_id": self.sender_id,
            "receiver_role": self.receiver_role.value,
            "receiver_id": self.receiver_id,
            "message_type": self.message_type.value,
            "content": self.content,
            "timestamp": self.timestamp,
            "round_number": self.round_number
        }


@dataclass
class NegotiationContext:
    """谈判上下文"""
    session_id: str
    client_id: str
    merchant_id: str
    item_name: str
    initial_price: float
    current_round: int = 0
    max_rounds: int = 10
    status: NegotiationStatus = NegotiationStatus.INITIATED
    messages: List[AgentMessage] = None
    best_offer: Optional[float] = None
    agreement_price: Optional[float] = None
    created_at: float = None
    
    def __post_init__(self):
        if self.messages is None:
            self.messages = []
        if self.created_at is None:
            self.created_at = time.time()
