"""
Project Claw Agent通信系统 - 完整实现
文件位置：cloud_server/agent_system.py
"""

import asyncio
import logging
import time
import uuid
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class ClientAgent:
    """C端Agent"""
    
    def __init__(self, client_id: str, price_sensitivity: float = 0.7):
        self.client_id = client_id
        self.price_sensitivity = price_sensitivity
        self.history = []
    
    async def handle_offer(self, session_id: str, merchant_id: str, offered: float, expected: float, round_num: int):
        """处理报价"""
        diff = (offered - expected) / expected if expected else 0
        
        if diff <= 0.05:
            return self._create_message(session_id, merchant_id, "ACCEPTANCE", {"agreed_price": offered}, round_num)
        elif diff <= 0.15:
            counter = expected * (0.95 if self.price_sensitivity > 0.7 else 0.98)
            return self._create_message(session_id, merchant_id, "COUNTER_OFFER", {"counter_price": counter}, round_num)
        else:
            return self._create_message(session_id, merchant_id, "REJECTION", {"reason": "价格太高"}, round_num)
    
    async def handle_counter(self, session_id: str, merchant_id: str, counter: float, expected: float, round_num: int):
        """处理反价"""
        if counter <= expected * 1.2:
            new_counter = expected * 0.95
            return self._create_message(session_id, merchant_id, "COUNTER_OFFER", {"counter_price": new_counter}, round_num)
        return self._create_message(session_id, merchant_id, "REJECTION", {"reason": "无法接受"}, round_num)
    
    def _create_message(self, session_id: str, merchant_id: str, msg_type: str, content: Dict, round_num: int):
        """创建消息"""
        msg = {
            "message_id": str(uuid.uuid4()),
            "session_id": session_id,
            "sender_role": "CLIENT_AGENT",
            "sender_id": self.client_id,
            "receiver_id": merchant_id,
            "message_type": msg_type,
            "content": content,
            "timestamp": time.time(),
            "round_number": round_num
        }
        self.history.append(msg)
        logger.info(f"C端Agent {self.client_id} 发送 {msg_type}")
        return msg
    
    async def start(self, session_id: str, merchant_id: str, item: str, price: float):
        """启动询价"""
        return self._create_message(
            session_id, merchant_id, "INQUIRY",
            {"item_name": item, "expected_price": price}, 1
        )


class MerchantAgent:
    """B端Agent"""
    
    def __init__(self, merchant_id: str, base_price: float, strategy: str = "normal"):
        self.merchant_id = merchant_id
        self.base_price = base_price
        self.strategy = strategy
        self.min_price = base_price * 0.85
        self.history = []
    
    async def handle_inquiry(self, session_id: str, client_id: str, expected: float, round_num: int):
        """处理询价"""
        if self.strategy == "aggressive":
            offered = self.base_price * 0.98
        elif self.strategy == "conservative":
            offered = self.base_price * 1.05
        else:
            offered = self.base_price
        
        if expected and expected < self.min_price:
            offered = self.min_price * 1.02
        
        return self._create_message(
            session_id, client_id, "OFFER",
            {"offered_price": offered, "expected_price": expected}, round_num
        )
    
    async def handle_counter(self, session_id: str, client_id: str, counter: float, round_num: int):
        """处理反价"""
        if counter >= self.min_price:
            return self._create_message(
                session_id, client_id, "ACCEPTANCE",
                {"agreed_price": counter}, round_num
            )
        else:
            new_price = (counter + self.min_price) / 2
            return self._create_message(
                session_id, client_id, "COUNTER_OFFER",
                {"counter_price": new_price}, round_num
            )
    
    async def handle_acceptance(self, session_id: str, client_id: str, agreed_price: float, round_num: int):
        """处理接受"""
        return self._create_message(
            session_id, client_id, "FINAL_DECISION",
            {"status": "confirmed", "agreed_price": agreed_price, "order_id": str(uuid.uuid4())},
            round_num
        )
    
    async def handle_rejection(self, session_id: str, client_id: str, round_num: int):
        """处理拒绝"""
        return self._create_message(
            session_id, client_id, "OFFER",
            {"offered_price": self.min_price * 1.01}, round_num
        )
    
    def _create_message(self, session_id: str, client_id: str, msg_type: str, content: Dict, round_num: int):
        """创建消息"""
        msg = {
            "message_id": str(uuid.uuid4()),
            "session_id": session_id,
            "sender_role": "MERCHANT_AGENT",
            "sender_id": self.merchant_id,
            "receiver_id": client_id,
            "message_type": msg_type,
            "content": content,
            "timestamp": time.time(),
            "round_number": round_num
        }
        self.history.append(msg)
        logger.info(f"B端Agent {self.merchant_id} 发送 {msg_type}")
        return msg


class NegotiationOrchestrator:
    """谈判协调器"""
    
    def __init__(self):
        self.clients: Dict[str, ClientAgent] = {}
        self.merchants: Dict[str, MerchantAgent] = {}
        self.negotiations: Dict[str, Dict] = {}
    
    async def start_negotiation(
        self, client_id: str, merchant_id: str, item: str, price: float,
        client_profile: Dict = None, merchant_profile: Dict = None
    ) -> str:
        """启动谈判"""
        session_id = str(uuid.uuid4())
        
        if client_id not in self.clients:
            profile = client_profile or {}
            self.clients[client_id] = ClientAgent(client_id, profile.get("price_sensitivity", 0.7))
        
        if merchant_id not in self.merchants:
            profile = merchant_profile or {}
            self.merchants[merchant_id] = MerchantAgent(merchant_id, price * 1.1, profile.get("strategy", "normal"))
        
        self.negotiations[session_id] = {
            "client_id": client_id, "merchant_id": merchant_id, "item": item, "price": price,
            "messages": [], "status": "in_progress", "round": 0, "max_rounds": 10
        }
        
        logger.info(f"启动谈判: {session_id}")
        return session_id
    
    async def run_negotiation(self, session_id: str) -> Tuple[bool, Optional[float]]:
        """运行谈判"""
        neg = self.negotiations.get(session_id)
        if not neg:
            return False, None
        
        client = self.clients[neg["client_id"]]
        merchant = self.merchants[neg["merchant_id"]]
        
        # C端发起询价
        msg = await client.start(session_id, neg["merchant_id"], neg["item"], neg["price"])
        neg["messages"].append(msg)
        neg["round"] = 1
        
        # 谈判循环
        while neg["round"] < neg["max_rounds"]:
            last_msg = neg["messages"][-1]
            
            # B端处理
            if last_msg["message_type"] == "INQUIRY":
                merchant_msg = await merchant.handle_inquiry(
                    session_id, neg["client_id"], last_msg["content"].get("expected_price"), last_msg["round_number"] + 1
                )
            elif last_msg["message_type"] == "COUNTER_OFFER":
                merchant_msg = await merchant.handle_counter(
                    session_id, neg["client_id"], last_msg["content"].get("counter_price"), last_msg["round_number"] + 1
                )
            elif last_msg["message_type"] == "ACCEPTANCE":
                merchant_msg = await merchant.handle_acceptance(
                    session_id, neg["client_id"], last_msg["content"].get("agreed_price"), last_msg["round_number"] + 1
                )
            elif last_msg["message_type"] == "REJECTION":
                merchant_msg = await merchant.handle_rejection(session_id, neg["client_id"], last_msg["round_number"] + 1)
            else:
                neg["status"] = "failed"
                return False, None
            
            neg["messages"].append(merchant_msg)
            neg["round"] += 1
            
            if merchant_msg["message_type"] == "ACCEPTANCE":
                neg["status"] = "agreed"
                price = merchant_msg["content"].get("agreed_price")
                logger.info(f"谈判成功: {session_id}, 价格: {price}")
                return True, price
            
            # C端处理
            last_msg = merchant_msg
            if last_msg["message_type"] == "OFFER":
                client_msg = await client.handle_offer(
                    session_id, neg["merchant_id"],
                    last_msg["content"].get("offered_price"),
                    last_msg["content"].get("expected_price"),
                    last_msg["round_number"] + 1
                )
            elif last_msg["message_type"] == "COUNTER_OFFER":
                client_msg = await client.handle_counter(
                    session_id, neg["merchant_id"],
                    last_msg["content"].get("counter_price"),
                    neg["price"],
                    last_msg["round_number"] + 1
                )
            else:
                neg["status"] = "failed"
                return False, None
            
            neg["messages"].append(client_msg)
            neg["round"] += 1
            
            if client_msg["message_type"] == "ACCEPTANCE":
                neg["status"] = "agreed"
                price = client_msg["content"].get("agreed_price")
                logger.info(f"谈判成功: {session_id}, 价格: {price}")
                return True, price
            
            if client_msg["message_type"] == "REJECTION":
                neg["status"] = "failed"
                logger.warning(f"谈判失败: {session_id}")
                return False, None
            
            await asyncio.sleep(0.1)
        
        neg["status"] = "timeout"
        return False, None
    
    def get_history(self, session_id: str) -> list:
        """获取历史"""
        neg = self.negotiations.get(session_id)
        return neg["messages"] if neg else []
    
    def get_status(self, session_id: str) -> Dict:
        """获取状态"""
        neg = self.negotiations.get(session_id)
        if not neg:
            return {}
        return {
            "session_id": session_id,
            "client_id": neg["client_id"],
            "merchant_id": neg["merchant_id"],
            "status": neg["status"],
            "round": neg["round"],
            "messages": len(neg["messages"])
        }
