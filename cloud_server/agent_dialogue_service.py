"""
Project Claw Agent 对话系统 - C端Agent和B端Agent通信实现
文件位置：cloud_server/agent_dialogue_service.py
"""

import asyncio
import json
import time
from typing import Dict, List, Optional
from datetime import datetime
import httpx
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════

class ClientProfile(BaseModel):
    """C端用户画像"""
    client_id: str
    price_sensitivity: float  # 0-1，越高越敏感
    time_urgency: float       # 0-1，越高越急
    quality_preference: float # 0-1，越高越看重质量
    brand_preferences: List[str] = []
    purchase_history: List[Dict] = []
    location: str = ""
    created_at: float = None
    
    def __init__(self, **data):
        super().__init__(**data)
        if self.created_at is None:
            self.created_at = time.time()


class MerchantProfile(BaseModel):
    """B端商家画像"""
    merchant_id: str
    shop_name: str
    inventory: Dict[str, int] = {}  # 商品库存
    pricing_strategy: str = "normal"  # normal, aggressive, conservative
    service_rating: float = 5.0
    response_speed: float = 1.0  # 秒
    negotiation_style: str = "friendly"  # friendly, strict, flexible
    created_at: float = None
    
    def __init__(self, **data):
        super().__init__(**data)
        if self.created_at is None:
            self.created_at = time.time()


class DialogueTurn(BaseModel):
    """对话轮次"""
    session_id: str
    turn_id: int
    speaker: str  # "client_agent" or "merchant_agent"
    text: str
    timestamp: float
    metadata: Dict = {}


class DialogueSession(BaseModel):
    """对话会话"""
    session_id: str
    client_id: str
    merchant_id: str
    item_name: str
    expected_price: float
    turns: List[DialogueTurn] = []
    status: str = "active"  # active, completed, failed
    best_offer: Optional[Dict] = None
    created_at: float = None
    
    def __init__(self, **data):
        super().__init__(**data)
        if self.created_at is None:
            self.created_at = time.time()


# ═══════════════════════════════════════════════════════════════
# C端Agent（客户端谈判Agent）
# ═══════════════════════════════════════════════════════════════

class ClientAgent:
    """C端Agent - 代表客户进行谈判"""
    
    def __init__(self, client_profile: ClientProfile, llm_client):
        self.profile = client_profile
        self.llm_client = llm_client
        self.negotiation_history = []
    
    async def generate_opening_message(self, item_name: str, expected_price: float) -> str:
        """生成开场白"""
        prompt = f"""
        你是一个聪明的购物者，正在与商家谈判购买 {item_name}。
        
        你的个性：
        - 价格敏感度：{self.profile.price_sensitivity * 100:.0f}%
        - 时间紧急度：{self.profile.time_urgency * 100:.0f}%
        - 质量偏好：{self.profile.quality_preference * 100:.0f}%
        
        你的预算：¥{expected_price}
        
        请生成一个友好但坚定的开场白，表达你的购买意图和预算。
        回复应该简短（不超过50字）。
        """
        
        response = await self.llm_client.chat(prompt)
        return response
    
    async def generate_counter_offer(self, merchant_offer: str, item_name: str, expected_price: float) -> str:
        """生成反价"""
        prompt = f"""
        商家的报价：{merchant_offer}
        
        你的预算：¥{expected_price}
        你的价格敏感度：{self.profile.price_sensitivity * 100:.0f}%
        
        请生成一个合理的反价或讨价还价的理由。
        如果商家的价格接近你的预算，可以考虑接受。
        回复应该简短（不超于50字）。
        """
        
        response = await self.llm_client.chat(prompt)
        return response
    
    async def evaluate_offer(self, offer_price: float, expected_price: float) -> Dict:
        """评估报价"""
        discount_rate = (expected_price - offer_price) / expected_price if expected_price > 0 else 0
        
        # 根据个性化设置评估
        if offer_price <= expected_price:
            satisfaction = 0.9 + (discount_rate * 0.1)
        else:
            # 如果超过预算，根据时间紧急度调整
            satisfaction = max(0.3, 1 - (offer_price - expected_price) / expected_price * (1 - self.profile.time_urgency))
        
        return {
            "offer_price": offer_price,
            "expected_price": expected_price,
            "discount_rate": discount_rate,
            "satisfaction": min(1.0, satisfaction),
            "accept": satisfaction > 0.6
        }


# ═══════════════════════════════════════════════════════════════
# B端Agent（商家谈判Agent）
# ═══════════════════════════════════════════════════════════════

class MerchantAgent:
    """B端Agent - 代表商家进行谈判"""
    
    def __init__(self, merchant_profile: MerchantProfile, llm_client):
        self.profile = merchant_profile
        self.llm_client = llm_client
        self.negotiation_history = []
    
    async def generate_initial_offer(self, item_name: str, base_price: float, client_profile: ClientProfile) -> Dict:
        """生成初始报价"""
        # 根据商家策略调整价格
        if self.profile.pricing_strategy == "aggressive":
            offer_price = base_price * 1.1
        elif self.profile.pricing_strategy == "conservative":
            offer_price = base_price * 0.95
        else:
            offer_price = base_price
        
        # 根据客户画像调整
        if client_profile.price_sensitivity > 0.7:
            offer_price *= 0.95  # 对价格敏感的客户给予折扣
        
        prompt = f"""
        你是一个商家，正在与客户谈判 {item_name} 的价格。
        
        你的商家风格：{self.profile.negotiation_style}
        基础价格：¥{base_price}
        建议报价：¥{offer_price:.2f}
        
        请生成一个吸引人的报价说辞，强调商品的价值。
        回复应该简短（不超过50字）。
        """
        
        response = await self.llm_client.chat(prompt)
        
        return {
            "offer_price": offer_price,
            "message": response,
            "timestamp": time.time()
        }
    
    async def respond_to_counter_offer(self, client_counter: str, current_offer: float, base_price: float) -> Dict:
        """响应客户的反价"""
        # 根据谈判风格调整
        if self.profile.negotiation_style == "flexible":
            new_offer = current_offer * 0.98  # 稍微降价
        elif self.profile.negotiation_style == "strict":
            new_offer = current_offer  # 坚持原价
        else:
            new_offer = current_offer * 0.99  # 友好地稍微降价
        
        # 确保不低于成本
        new_offer = max(new_offer, base_price * 0.85)
        
        prompt = f"""
        客户说：{client_counter}
        
        你的当前报价：¥{current_offer:.2f}
        你的新报价：¥{new_offer:.2f}
        
        请生成一个回应，解释为什么这是最好的价格。
        回复应该简短（不超过50字）。
        """
        
        response = await self.llm_client.chat(prompt)
        
        return {
            "new_offer": new_offer,
            "message": response,
            "timestamp": time.time()
        }


# ═══════════════════════════════════════════════════════════════
# 对话管理器
# ═══════════════════════════════════════════════════════════════

class DialogueManager:
    """管理C端Agent和B端Agent之间的对话"""
    
    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.sessions: Dict[str, DialogueSession] = {}
        self.client_profiles: Dict[str, ClientProfile] = {}
        self.merchant_profiles: Dict[str, MerchantProfile] = {}
    
    async def start_dialogue(
        self,
        session_id: str,
        client_id: str,
        merchant_id: str,
        item_name: str,
        expected_price: float,
        client_profile: ClientProfile,
        merchant_profile: MerchantProfile
    ) -> DialogueSession:
        """启动对话会话"""
        
        # 创建会话
        session = DialogueSession(
            session_id=session_id,
            client_id=client_id,
            merchant_id=merchant_id,
            item_name=item_name,
            expected_price=expected_price
        )
        
        # 保存画像
        self.client_profiles[client_id] = client_profile
        self.merchant_profiles[merchant_id] = merchant_profile
        
        # 创建Agent
        client_agent = ClientAgent(client_profile, self.llm_client)
        merchant_agent = MerchantAgent(merchant_profile, self.llm_client)
        
        # 生成开场白
        opening_message = await client_agent.generate_opening_message(item_name, expected_price)
        
        # 添加到会话
        session.turns.append(DialogueTurn(
            session_id=session_id,
            turn_id=0,
            speaker="client_agent",
            text=opening_message,
            timestamp=time.time()
        ))
        
        # 商家生成初始报价
        base_price = expected_price * 1.2  # 假设基础价格比预期高20%
        merchant_offer = await merchant_agent.generate_initial_offer(
            item_name,
            base_price,
            client_profile
        )
        
        session.turns.append(DialogueTurn(
            session_id=session_id,
            turn_id=1,
            speaker="merchant_agent",
            text=merchant_offer["message"],
            timestamp=time.time(),
            metadata={"offer_price": merchant_offer["offer_price"]}
        ))
        
        self.sessions[session_id] = session
        return session
    
    async def continue_dialogue(self, session_id: str, max_turns: int = 5) -> DialogueSession:
        """继续对话直到达成协议或达到最大轮数"""
        
        session = self.sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        client_profile = self.client_profiles[session.client_id]
        merchant_profile = self.merchant_profiles[session.merchant_id]
        
        client_agent = ClientAgent(client_profile, self.llm_client)
        merchant_agent = MerchantAgent(merchant_profile, self.llm_client)
        
        turn_id = len(session.turns)
        
        while turn_id < max_turns and session.status == "active":
            # 获取最后一条消息
            last_turn = session.turns[-1]
            
            if last_turn.speaker == "merchant_agent":
                # 客户响应
                counter_offer = await client_agent.generate_counter_offer(
                    last_turn.text,
                    session.item_name,
                    session.expected_price
                )
                
                session.turns.append(DialogueTurn(
                    session_id=session_id,
                    turn_id=turn_id,
                    speaker="client_agent",
                    text=counter_offer,
                    timestamp=time.time()
                ))
                
                # 评估是否接受
                merchant_offer_price = last_turn.metadata.get("offer_price", session.expected_price)
                evaluation = await client_agent.evaluate_offer(merchant_offer_price, session.expected_price)
                
                if evaluation["accept"]:
                    session.status = "completed"
                    session.best_offer = {
                        "price": merchant_offer_price,
                        "satisfaction": evaluation["satisfaction"]
                    }
                    break
            
            else:
                # 商家响应
                last_merchant_turn = next(
                    (t for t in reversed(session.turns) if t.speaker == "merchant_agent"),
                    None
                )
                
                if last_merchant_turn:
                    merchant_response = await merchant_agent.respond_to_counter_offer(
                        last_turn.text,
                        last_merchant_turn.metadata.get("offer_price", session.expected_price),
                        session.expected_price * 0.8
                    )
                    
                    session.turns.append(DialogueTurn(
                        session_id=session_id,
                        turn_id=turn_id,
                        speaker="merchant_agent",
                        text=merchant_response["message"],
                        timestamp=time.time(),
                        metadata={"offer_price": merchant_response["new_offer"]}
                    ))
            
            turn_id += 1
        
        if turn_id >= max_turns:
            session.status = "failed"
        
        return session
    
    def get_session(self, session_id: str) -> Optional[DialogueSession]:
        """获取对话会话"""
        return self.sessions.get(session_id)
    
    def get_session_history(self, session_id: str) -> List[Dict]:
        """获取对话历史"""
        session = self.sessions.get(session_id)
        if not session:
            return []
        
        return [
            {
                "turn_id": turn.turn_id,
                "speaker": turn.speaker,
                "text": turn.text,
                "timestamp": turn.timestamp,
                "metadata": turn.metadata
            }
            for turn in session.turns
        ]
