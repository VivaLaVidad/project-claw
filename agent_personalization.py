from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ClientProfile:
    """C端客户个性化画像"""

    client_id: str
    budget_min: float = 10.0
    budget_max: float = 50.0
    price_sensitivity: float = 0.8  # 0-1，越高越敏感
    time_urgency: float = 0.5  # 0-1，越高越急
    quality_preference: float = 0.6  # 0-1，越高越看重质量
    custom_tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "client_id": self.client_id,
            "budget_min": self.budget_min,
            "budget_max": self.budget_max,
            "price_sensitivity": self.price_sensitivity,
            "time_urgency": self.time_urgency,
            "quality_preference": self.quality_preference,
            "custom_tags": self.custom_tags,
        }


@dataclass
class MerchantProfile:
    """B端商家个性化画像"""

    merchant_id: str
    bottom_price: float = 8.0  # 底价（不能低于此）
    normal_price: float = 15.0  # 常规价
    max_discount_rate: float = 0.15  # 最大让价比例
    delivery_time_minutes: int = 15
    quality_score: float = 0.85  # 0-1，商品质量评分
    service_score: float = 0.80  # 0-1，服务评分
    inventory_status: dict[str, int] = field(default_factory=dict)  # 库存
    custom_tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "merchant_id": self.merchant_id,
            "bottom_price": self.bottom_price,
            "normal_price": self.normal_price,
            "max_discount_rate": self.max_discount_rate,
            "delivery_time_minutes": self.delivery_time_minutes,
            "quality_score": self.quality_score,
            "service_score": self.service_score,
            "inventory_status": self.inventory_status,
            "custom_tags": self.custom_tags,
        }


@dataclass
class NegotiationStrategy:
    """谈判策略配置"""

    max_rounds: int = 5  # 最多谈判轮数
    timeout_seconds: float = 30.0  # 单轮超时
    merchant_concession_per_round: float = 0.02  # 每轮让价幅度
    client_satisfaction_threshold: float = 0.75  # C端满意度阈值
    merchant_profit_threshold: float = 0.20  # B端利润率阈值

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_rounds": self.max_rounds,
            "timeout_seconds": self.timeout_seconds,
            "merchant_concession_per_round": self.merchant_concession_per_round,
            "client_satisfaction_threshold": self.client_satisfaction_threshold,
            "merchant_profit_threshold": self.merchant_profit_threshold,
        }


class PersonalizationEngine:
    """个性化引擎：根据 C/B 画像计算满意度和策略"""

    def __init__(self):
        self.clients: dict[str, ClientProfile] = {}
        self.merchants: dict[str, MerchantProfile] = {}
        self.strategies: dict[str, NegotiationStrategy] = {}

    def register_client(self, profile: ClientProfile) -> None:
        self.clients[profile.client_id] = profile

    def register_merchant(self, profile: MerchantProfile) -> None:
        self.merchants[profile.merchant_id] = profile

    def register_strategy(self, merchant_id: str, strategy: NegotiationStrategy) -> None:
        self.strategies[merchant_id] = strategy

    def calculate_client_satisfaction(
        self,
        client_id: str,
        offered_price: float,
        delivery_time: int,
        quality_score: float,
    ) -> dict[str, float]:
        """计算 C 端满意度（0-1）"""
        client = self.clients.get(client_id)
        if not client:
            return {"overall": 0.5, "price": 0.5, "time": 0.5, "quality": 0.5}

        # 价格满意度
        if offered_price <= client.budget_min:
            price_score = 1.0
        elif offered_price <= client.budget_max:
            price_score = 1.0 - (offered_price - client.budget_min) / (client.budget_max - client.budget_min) * 0.3
        else:
            price_score = 0.0

        # 时间满意度
        time_score = max(0.0, 1.0 - (delivery_time / 30.0) * client.time_urgency)

        # 质量满意度
        quality_score_val = quality_score * client.quality_preference + 0.5 * (1 - client.quality_preference)

        # 综合满意度
        overall = price_score * 0.5 + time_score * 0.2 + quality_score_val * 0.3

        return {
            "overall": round(overall, 3),
            "price": round(price_score, 3),
            "time": round(time_score, 3),
            "quality": round(quality_score_val, 3),
        }

    def calculate_merchant_profit(
        self,
        merchant_id: str,
        offered_price: float,
        cost_price: float = 5.0,
    ) -> dict[str, float]:
        """计算 B 端利润率"""
        merchant = self.merchants.get(merchant_id)
        if not merchant:
            return {"profit_rate": 0.0, "profit_amount": 0.0}

        profit_amount = offered_price - cost_price
        profit_rate = profit_amount / offered_price if offered_price > 0 else 0.0

        return {
            "profit_rate": round(profit_rate, 3),
            "profit_amount": round(profit_amount, 3),
        }

    def suggest_next_offer(
        self,
        merchant_id: str,
        client_id: str,
        current_round: int,
        client_expected_price: float,
    ) -> dict[str, Any]:
        """根据个性化画像建议下一轮报价"""
        merchant = self.merchants.get(merchant_id)
        client = self.clients.get(client_id)
        strategy = self.strategies.get(merchant_id, NegotiationStrategy())

        if not merchant or not client:
            return {"suggested_price": 15.0, "reason": "profile not found"}

        # 计算让价空间
        max_discount = merchant.normal_price * strategy.merchant_concession_per_round * current_round
        suggested_price = max(merchant.bottom_price, merchant.normal_price - max_discount)

        # 如果客户期望价格在可接受范围内，尽量靠近
        if merchant.bottom_price <= client_expected_price <= merchant.normal_price:
            suggested_price = min(suggested_price, client_expected_price)

        return {
            "suggested_price": round(suggested_price, 2),
            "bottom_price": merchant.bottom_price,
            "normal_price": merchant.normal_price,
            "reason": f"round {current_round}, client_sensitivity={client.price_sensitivity:.2f}",
        }
