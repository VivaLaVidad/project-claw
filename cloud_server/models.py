"""
Project Claw v14.3 - Database Models & Authentication
工业级 ORM + 微信认证 + 设备级 DID
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID, uuid4
from pydantic import BaseModel, Field
from sqlalchemy import Column, String, Float, Integer, DateTime, DECIMAL, JSON, LargeBinary, Index, ForeignKey, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, ARRAY
from sqlalchemy.ext.declarative import declarative_base
import hashlib
import hmac
import json

Base = declarative_base()

# ═══════════════════════════════════════════════════════════════════════════
# 👥 ORM Models
# ═══════════════════════════════════════════════════════════════════════════

class ClientModel(Base):
    """C端消费者模型"""
    __tablename__ = "clients"
    
    client_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    wechat_openid = Column(String(128), unique=True, nullable=False, index=True)
    wechat_unionid = Column(String(128))
    nickname = Column(String(64))
    avatar_url = Column(String(512))
    
    # 🔥 1024维用户画像向量
    persona_vector = Column(ARRAY(Float, dimensions=1))
    
    risk_score = Column(Integer, default=50)
    status = Column(String(32), default='active')
    
    total_trades = Column(Integer, default=0)
    total_spent = Column(DECIMAL(12, 2), default=0)
    avg_satisfaction = Column(Float, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MerchantModel(Base):
    """B端商家模型"""
    __tablename__ = "merchants"
    
    merchant_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # 🔥 裂变引擎：绑定的数字包工头 ID
    promoter_id = Column(String(64), index=True)
    
    merchant_name = Column(String(128), nullable=False)
    merchant_phone = Column(String(20))
    
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    address = Column(String(512))
    
    box_status = Column(String(32), default='offline', index=True)
    
    # 🔥 龙虾币余额
    routing_token_balance = Column(DECIMAL(12, 2), default=0)
    
    # 🔥 Tailscale 虚拟 IP
    tailscale_ip = Column(String(64), index=True)
    
    device_did_public_key = Column(String(2048))
    device_did_private_key_encrypted = Column(String(2048))
    
    # 商家画像向量
    merchant_vector = Column(ARRAY(Float, dimensions=1))
    
    total_offers = Column(Integer, default=0)
    total_accepted = Column(Integer, default=0)
    avg_response_time_ms = Column(Integer, default=0)
    
    business_license_url = Column(String(512))
    verified_at = Column(DateTime)
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TradeLedgerModel(Base):
    """交易流水表（金融级账本）"""
    __tablename__ = "trade_ledger"
    
    trade_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # 幂等性保证
    idempotency_key = Column(String(256), unique=True, nullable=False)
    
    # 全链路追踪
    trace_id = Column(String(256), index=True)
    
    client_id = Column(PG_UUID(as_uuid=True), ForeignKey('clients.client_id'), nullable=False, index=True)
    merchant_id = Column(PG_UUID(as_uuid=True), ForeignKey('merchants.merchant_id'), nullable=False, index=True)
    
    original_price = Column(DECIMAL(10, 2), nullable=False)
    final_price = Column(DECIMAL(10, 2), nullable=False)
    
    # 🔥 状态机
    status = Column(String(32), default='pending', index=True)
    
    # 🔥 审计哈希
    audit_hash = Column(String(256))
    
    # 分润
    platform_fee = Column(DECIMAL(10, 2))  # 1% 路由费
    promoter_commission = Column(DECIMAL(10, 2))  # 数字包工头分润
    
    # 支付
    wechat_trade_no = Column(String(256))
    payment_status = Column(String(32), default='unpaid')
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    negotiation_start_at = Column(DateTime)
    accepted_at = Column(DateTime)
    settled_at = Column(DateTime)


class NegotiationLogModel(Base):
    """A2A 谈判记录"""
    __tablename__ = "negotiation_log"
    
    negotiation_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    trade_id = Column(PG_UUID(as_uuid=True), ForeignKey('trade_ledger.trade_id'), nullable=False, index=True)
    
    round = Column(Integer, nullable=False)
    speaker_role = Column(String(32))  # 'client' / 'merchant' / 'agent'
    
    message = Column(String(2048), nullable=False)
    suggested_price = Column(DECIMAL(10, 2))
    
    model_name = Column(String(64))
    inference_time_ms = Column(Integer)
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


# ═══════════════════════════════════════════════════════════════════════════
# 🔐 认证系统
# ═══════════════════════════════════════════════════════════════════════════

class WeChatAuthService:
    """微信 OpenID 静默认证"""
    
    def __init__(self, wechat_app_id: str, wechat_app_secret: str):
        self.app_id = wechat_app_id
        self.app_secret = wechat_app_secret
    
    async def exchange_code_for_openid(self, code: str) -> dict:
        """
        用 wx.login 返回的 code 换取 OpenID
        
        微信小程序流程：
        1. 前端调用 wx.login() 获取 code
        2. 前端将 code 发送到后端
        3. 后端用 code + app_id + app_secret 向微信服务器换取 openid
        4. 后端生成 JWT Token 返回给前端
        """
        import httpx
        
        url = "https://api.weixin.qq.com/sns/jscode2session"
        params = {
            "appid": self.app_id,
            "secret": self.app_secret,
            "js_code": code,
            "grant_type": "authorization_code"
        }
        
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params, timeout=10)
            data = resp.json()
        
        if "errcode" in data:
            raise ValueError(f"WeChat API error: {data.get('errmsg')}")
        
        return {
            "openid": data["openid"],
            "unionid": data.get("unionid"),
            "session_key": data["session_key"]
        }


class DeviceDIDAuthService:
    """设备级 DID 认证（龙虾盒子）"""
    
    @staticmethod
    def generate_keypair() -> tuple[str, str]:
        """生成 RSA 密钥对"""
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
        
        public_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode()
        
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ).decode()
        
        return public_pem, private_pem
    
    @staticmethod
    def sign_heartbeat(device_sn: str, timestamp: int, private_key_pem: str) -> str:
        """
        龙虾盒子签名心跳包
        
        盒子开机自动：
        1. 生成当前时间戳
        2. 用私钥签名 "device_sn:timestamp"
        3. 发送签名到 Railway
        4. Railway 用公钥验证签名
        """
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.backends import default_backend
        
        message = f"{device_sn}:{timestamp}".encode()
        
        private_key = serialization.load_pem_private_key(
            private_key_pem.encode(),
            password=None,
            backend=default_backend()
        )
        
        signature = private_key.sign(
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        
        return signature.hex()
    
    @staticmethod
    def verify_heartbeat(device_sn: str, timestamp: int, signature: str, public_key_pem: str) -> bool:
        """验证盒子签名"""
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.backends import default_backend
        
        message = f"{device_sn}:{timestamp}".encode()
        
        public_key = serialization.load_pem_public_key(
            public_key_pem.encode(),
            backend=default_backend()
        )
        
        try:
            public_key.verify(
                bytes.fromhex(signature),
                message,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            return True
        except:
            return False


# ═══════════════════════════════════════════════════════════════════════════
# 📊 Pydantic 数据模型（API 请求/响应）
# ═══════════════════════════════════════════════════════════════════════════

class ClientAuthRequest(BaseModel):
    """C端认证请求"""
    code: str = Field(..., description="wx.login 返回的 code")


class ClientAuthResponse(BaseModel):
    """C端认证响应"""
    client_id: str
    token: str
    expires_in: int


class MerchantHeartbeatRequest(BaseModel):
    """B端心跳请求"""
    device_sn: str
    timestamp: int
    signature: str  # 用私钥签名的 "device_sn:timestamp"


class TradeRequestPayload(BaseModel):
    """交易请求"""
    request_id: str
    trace_id: str
    idempotency_key: str
    client_id: str
    item_name: str
    demand_text: str
    max_price: float
    quantity: int = 1
    timeout_sec: float = 20


class TradeSettlementPayload(BaseModel):
    """交易结算（金融级）"""
    trade_id: str
    idempotency_key: str
    final_price: float
    merchant_id: str
    client_id: str
    
    # 审计字段
    audit_hash: str  # SHA256(trade_id + final_price + timestamp)
    
    # 分润
    platform_fee: float  # 1% 路由费
    promoter_commission: float  # 数字包工头分润


def generate_audit_hash(trade_id: str, final_price: float, timestamp: int) -> str:
    """生成不可篡改的审计哈希"""
    message = f"{trade_id}:{final_price}:{timestamp}".encode()
    return hashlib.sha256(message).hexdigest()
