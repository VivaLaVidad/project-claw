"""
Project Claw v14.3 - WeChat Payment V3 Profit Sharing
微信支付服务商分账 API：实现 1% 路由费 + 数字包工头分润
"""

import asyncio
import hashlib
import hmac
import json
import time
from typing import Optional
from datetime import datetime
import httpx
from pydantic import BaseModel, Field


class WeChatPaymentV3Service:
    """
    微信支付 V3 服务商分账
    
    商业模式：
    - 用户支付 20 元
    - 微信底层直接切出 19.8 元给商家
    - 0.2 元（1%）给平台
    - 其中 0.12 元给数字包工头（60% 分润）
    - 0.08 元给平台（40% 分润）
    """
    
    def __init__(
        self,
        mch_id: str,  # 商户号
        mch_serial_no: str,  # 商户证书序列号
        api_v3_key: str,  # API v3 密钥
        private_key_path: str,  # 商户私钥路径
    ):
        self.mch_id = mch_id
        self.mch_serial_no = mch_serial_no
        self.api_v3_key = api_v3_key
        self.private_key_path = private_key_path
        
        # 读取私钥
        with open(private_key_path, 'r') as f:
            self.private_key = f.read()
    
    def _build_authorization_header(self, method: str, url_path: str, body: str = "") -> str:
        """
        构建微信支付 V3 授权头
        
        签名算法：
        1. 构建签名字符串：method\nurl_path\ntimestamp\nnonce\nbody\n
        2. 用商户私钥签名
        3. 生成 Authorization 头
        """
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.backends import default_backend
        import base64
        import uuid
        
        timestamp = str(int(time.time()))
        nonce = str(uuid.uuid4())
        
        # 构建签名字符串
        sign_str = f"{method}\n{url_path}\n{timestamp}\n{nonce}\n{body}\n"
        
        # 加载私钥
        private_key = serialization.load_pem_private_key(
            self.private_key.encode(),
            password=None,
            backend=default_backend()
        )
        
        # 签名
        signature = private_key.sign(
            sign_str.encode(),
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        
        signature_b64 = base64.b64encode(signature).decode()
        
        # 构建 Authorization 头
        auth_header = f'WECHATPAY2-SHA256-RSA2048 mchid="{self.mch_id}",nonce_str="{nonce}",timestamp="{timestamp}",serial_no="{self.mch_serial_no}",signature="{signature_b64}"'
        
        return auth_header
    
    async def create_order(
        self,
        trade_id: str,
        client_openid: str,
        amount_cents: int,  # 金额（分）
        description: str,
        notify_url: str,
    ) -> dict:
        """
        创建微信支付订单
        
        参数：
        - trade_id: 平台订单号
        - client_openid: 用户 OpenID
        - amount_cents: 金额（分）
        - description: 商品描述
        - notify_url: 支付回调 URL
        """
        url = "https://api.mch.weixin.qq.com/v3/pay/transactions/jsapi"
        
        body = {
            "mchid": self.mch_id,
            "out_trade_no": trade_id,
            "appid": "YOUR_APPID",  # 从环境变量读取
            "description": description,
            "notify_url": notify_url,
            "amount": {
                "total": amount_cents,
                "currency": "CNY"
            },
            "payer": {
                "openid": client_openid
            }
        }
        
        body_str = json.dumps(body)
        auth_header = self._build_authorization_header("POST", "/v3/pay/transactions/jsapi", body_str)
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                headers={"Authorization": auth_header},
                content=body_str,
                timeout=10
            )
        
        if resp.status_code != 200:
            raise ValueError(f"WeChat API error: {resp.text}")
        
        return resp.json()
    
    async def profit_sharing(
        self,
        trade_id: str,
        wechat_trade_no: str,
        merchant_id: str,
        merchant_account: str,  # 商家微信账户
        amount_cents: int,  # 分账金额（分）
        description: str = "商家分账",
    ) -> dict:
        """
        分账：将钱分给商家
        
        流程：
        1. 用户支付 20 元 → 微信冻结 20 元
        2. 调用分账 API → 微信解冻 19.8 元 给商家
        3. 平台保留 0.2 元（1% 路由费）
        """
        url = "https://api.mch.weixin.qq.com/v3/profitsharing/orders"
        
        body = {
            "transaction_id": wechat_trade_no,
            "out_order_no": f"{trade_id}_share",
            "receivers": [
                {
                    "type": "MERCHANT_ID",
                    "account": merchant_account,
                    "amount": amount_cents,
                    "description": description
                }
            ]
        }
        
        body_str = json.dumps(body)
        auth_header = self._build_authorization_header("POST", "/v3/profitsharing/orders", body_str)
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                headers={"Authorization": auth_header},
                content=body_str,
                timeout=10
            )
        
        if resp.status_code != 200:
            raise ValueError(f"WeChat API error: {resp.text}")
        
        return resp.json()
    
    async def promoter_profit_sharing(
        self,
        trade_id: str,
        wechat_trade_no: str,
        promoter_id: str,
        promoter_account: str,  # 数字包工头微信账户
        amount_cents: int,  # 分账金额（分）
    ) -> dict:
        """
        二级分账：将钱分给数字包工头
        
        流程：
        1. 商家收到 19.8 元
        2. 商家再分出 0.12 元（60% 分润）给数字包工头
        3. 商家保留 19.68 元
        """
        url = "https://api.mch.weixin.qq.com/v3/profitsharing/orders"
        
        body = {
            "transaction_id": wechat_trade_no,
            "out_order_no": f"{trade_id}_promoter",
            "receivers": [
                {
                    "type": "MERCHANT_ID",
                    "account": promoter_account,
                    "amount": amount_cents,
                    "description": f"数字包工头分润 - {promoter_id}"
                }
            ]
        }
        
        body_str = json.dumps(body)
        auth_header = self._build_authorization_header("POST", "/v3/profitsharing/orders", body_str)
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                headers={"Authorization": auth_header},
                content=body_str,
                timeout=10
            )
        
        if resp.status_code != 200:
            raise ValueError(f"WeChat API error: {resp.text}")
        
        return resp.json()
    
    async def query_order(self, trade_id: str) -> dict:
        """查询订单状态"""
        url = f"https://api.mch.weixin.qq.com/v3/pay/transactions/out-trade-no/{trade_id}"
        
        params = {"mchid": self.mch_id}
        
        auth_header = self._build_authorization_header("GET", f"/v3/pay/transactions/out-trade-no/{trade_id}?mchid={self.mch_id}")
        
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url,
                headers={"Authorization": auth_header},
                params=params,
                timeout=10
            )
        
        if resp.status_code != 200:
            raise ValueError(f"WeChat API error: {resp.text}")
        
        return resp.json()


class PaymentFlowOrchestrator:
    """
    支付流程编排器
    
    完整流程：
    1. 用户在小程序选择商家报价
    2. 调用 create_order → 微信支付
    3. 用户支付成功 → 微信回调
    4. 调用 profit_sharing → 分账给商家
    5. 调用 promoter_profit_sharing → 分账给数字包工头
    6. 更新 TradeLedger 状态为 SETTLED
    """
    
    def __init__(self, payment_service: WeChatPaymentV3Service):
        self.payment = payment_service
    
    async def execute_full_payment_flow(
        self,
        trade_id: str,
        client_openid: str,
        merchant_id: str,
        merchant_account: str,
        promoter_id: str,
        promoter_account: str,
        final_price: float,  # 元
        description: str,
        notify_url: str,
    ) -> dict:
        """
        执行完整支付流程
        
        金额分配（以 20 元为例）：
        - 用户支付：20 元
        - 商家收到：19.8 元（1% 路由费给平台）
        - 数字包工头分润：0.12 元（来自商家的 60% 分润）
        - 平台保留：0.08 元（40% 分润）
        """
        
        amount_cents = int(final_price * 100)
        platform_fee_cents = int(amount_cents * 0.01)  # 1% 路由费
        merchant_amount_cents = amount_cents - platform_fee_cents
        promoter_amount_cents = int(merchant_amount_cents * 0.006)  # 0.6% 给数字包工头
        
        try:
            # 1. 创建订单
            order_resp = await self.payment.create_order(
                trade_id=trade_id,
                client_openid=client_openid,
                amount_cents=amount_cents,
                description=description,
                notify_url=notify_url
            )
            
            wechat_trade_no = order_resp.get("transaction_id")
            
            # 2. 分账给商家
            merchant_share_resp = await self.payment.profit_sharing(
                trade_id=trade_id,
                wechat_trade_no=wechat_trade_no,
                merchant_id=merchant_id,
                merchant_account=merchant_account,
                amount_cents=merchant_amount_cents,
                description="商家分账"
            )
            
            # 3. 分账给数字包工头
            promoter_share_resp = await self.payment.promoter_profit_sharing(
                trade_id=trade_id,
                wechat_trade_no=wechat_trade_no,
                promoter_id=promoter_id,
                promoter_account=promoter_account,
                amount_cents=promoter_amount_cents
            )
            
            return {
                "status": "success",
                "trade_id": trade_id,
                "wechat_trade_no": wechat_trade_no,
                "total_amount": final_price,
                "platform_fee": platform_fee_cents / 100,
                "merchant_amount": merchant_amount_cents / 100,
                "promoter_commission": promoter_amount_cents / 100,
                "order_resp": order_resp,
                "merchant_share_resp": merchant_share_resp,
                "promoter_share_resp": promoter_share_resp
            }
        
        except Exception as e:
            return {
                "status": "failed",
                "trade_id": trade_id,
                "error": str(e)
            }


# ═══════════════════════════════════════════════════════════════════════════
# 📊 Pydantic 数据模型
# ═══════════════════════════════════════════════════════════════════════════

class PaymentNotificationRequest(BaseModel):
    """微信支付回调通知"""
    id: str
    create_time: str
    event_type: str
    resource_type: str
    summary: str
    resource: dict


class ProfitSharingRequest(BaseModel):
    """分账请求"""
    trade_id: str
    merchant_id: str
    merchant_account: str
    promoter_id: str
    promoter_account: str
    final_price: float
    description: str = "商品购买"
