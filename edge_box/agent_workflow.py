"""
agent_workflow.py - NegotiatorNode 动态博弈效用函数重构
时间权重因子 + 策略计算器 + 强制底线拦截
"""

import asyncio
import re
import logging
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class TimeSlot(str, Enum):
    """时间段"""
    PEAK_LUNCH = "peak_lunch"      # 12:00-13:00 午餐高峰
    OFF_PEAK = "off_peak"          # 14:00-17:00 闲时
    DINNER_PEAK = "dinner_peak"    # 18:00-20:00 晚餐高峰
    NORMAL = "normal"              # 其他时间


@dataclass
class DynamicUtility:
    """动态效用函数"""
    time_slot: TimeSlot
    price_adjustment: float        # 价格调整比例
    attitude_hardness: float       # 态度强硬度（0-1）
    negotiation_rounds: int        # 谈判轮数
    confidence: float              # 置信度


class StrategyCalculator:
    """策略计算器 - 基于时间的动态定价"""
    
    def __init__(self):
        self.time_weights = {
            TimeSlot.PEAK_LUNCH: {
                'price_adjustment': 0.05,      # 底线上浮 5%
                'attitude_hardness': 0.8,      # 态度强硬
                'reason': '午餐高峰期，客流量大'
            },
            TimeSlot.OFF_PEAK: {
                'price_adjustment': -0.10,     # 底线下调 10%
                'attitude_hardness': 0.3,      # 态度温和
                'reason': '下午闲时，需要吸引客流'
            },
            TimeSlot.DINNER_PEAK: {
                'price_adjustment': 0.08,      # 底线上浮 8%
                'attitude_hardness': 0.7,      # 态度较硬
                'reason': '晚餐高峰期，客流量大'
            },
            TimeSlot.NORMAL: {
                'price_adjustment': 0.0,       # 底线不变
                'attitude_hardness': 0.5,      # 态度中立
                'reason': '正常时段'
            }
        }
    
    def get_current_time_slot(self) -> TimeSlot:
        """获取当前时间段"""
        now = datetime.now()
        hour = now.hour
        
        if 12 <= hour < 13:
            return TimeSlot.PEAK_LUNCH
        elif 14 <= hour < 17:
            return TimeSlot.OFF_PEAK
        elif 18 <= hour < 20:
            return TimeSlot.DINNER_PEAK
        else:
            return TimeSlot.NORMAL
    
    def calculate_dynamic_utility(
        self,
        base_bottom_price: float,
        negotiation_round: int = 1
    ) -> DynamicUtility:
        """
        计算动态效用函数
        
        Args:
            base_bottom_price: 基础底价
            negotiation_round: 谈判轮数
        
        Returns:
            动态效用对象
        """
        time_slot = self.get_current_time_slot()
        weights = self.time_weights[time_slot]
        
        # 计算调整后的底价
        price_adjustment = weights['price_adjustment']
        adjusted_bottom_price = base_bottom_price * (1 + price_adjustment)
        
        # 随着谈判轮数增加，态度逐渐软化
        attitude_hardness = weights['attitude_hardness']
        if negotiation_round > 1:
            attitude_hardness *= (1 - 0.1 * (negotiation_round - 1))
            attitude_hardness = max(0.1, attitude_hardness)  # 最低 0.1
        
        # 置信度随轮数增加而增加
        confidence = min(0.95, 0.5 + 0.15 * negotiation_round)
        
        return DynamicUtility(
            time_slot=time_slot,
            price_adjustment=price_adjustment,
            attitude_hardness=attitude_hardness,
            negotiation_rounds=negotiation_round,
            confidence=confidence
        )
    
    def get_strategy_prompt(self, utility: DynamicUtility, base_price: float) -> str:
        """
        生成策略提示词
        
        Args:
            utility: 动态效用对象
            base_price: 基础底价
        
        Returns:
            策略提示词
        """
        adjusted_price = base_price * (1 + utility.price_adjustment)
        
        attitude_desc = {
            0.8: "非常强硬，寸步不让",
            0.7: "较为强硬，有原则",
            0.5: "中立态度，灵活应对",
            0.3: "温和态度，主动让步",
            0.1: "非常温和，积极成交"
        }
        
        # 找最接近的态度描述
        closest_hardness = min(attitude_desc.keys(), key=lambda x: abs(x - utility.attitude_hardness))
        attitude_text = attitude_desc[closest_hardness]
        
        prompt = f"""
【时间权重因子】
当前时间段: {utility.time_slot.value}
价格调整: {utility.price_adjustment:+.1%}
调整后底线: ¥{adjusted_price:.2f}
态度强硬度: {utility.attitude_hardness:.1%} ({attitude_text})
谈判轮数: {第 utility.negotiation_rounds} 轮
置信度: {utility.confidence:.1%}

【谈判策略】
1. 底线价格: ¥{adjusted_price:.2f}（绝不低于此价）
2. 态度: {attitude_text}
3. 让步空间: ¥{(adjusted_price * 0.05):.2f}（最多让步 5%）
4. 成交目标: ¥{(adjusted_price * 1.02):.2f}（理想成交价）

【强制要求】
- 任何报价都不能低于 ¥{adjusted_price:.2f}
- 如果客户坚持低于底线，拒绝成交
- 保持 {attitude_text} 的态度
"""
        return prompt


class PriceExtractor:
    """价格提取器 - 从 LLM 回复中提取报价"""
    
    @staticmethod
    def extract_price(text: str) -> Optional[float]:
        """
        从文本中提取价格
        
        Args:
            text: LLM 回复文本
        
        Returns:
            提取的价格，如果未找到返回 None
        """
        # 匹配各种价格格式
        patterns = [
            r'¥\s*(\d+\.?\d*)',           # ¥12.5
            r'￥\s*(\d+\.?\d*)',           # ￥12.5
            r'价格.*?(\d+\.?\d*)',         # 价格12.5
            r'报价.*?(\d+\.?\d*)',         # 报价12.5
            r'(\d+\.?\d*)\s*元',           # 12.5元
            r'(\d+\.?\d*)\s*块',           # 12.5块
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    price = float(match.group(1))
                    if 0 < price < 10000:  # 合理的价格范围
                        return price
                except ValueError:
                    continue
        
        return None


class AuditNode:
    """审计节点 - 强制底线拦截"""
    
    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
        self.price_extractor = PriceExtractor()
    
    async def audit_and_validate(
        self,
        llm_response: str,
        minimum_price: float,
        retry_callback=None
    ) -> Tuple[bool, Optional[float], str]:
        """
        审计和验证 LLM 回复
        
        Args:
            llm_response: LLM 回复文本
            minimum_price: 最低底线价格
            retry_callback: 重试回调函数
        
        Returns:
            (是否通过, 提取的价格, 审计信息)
        """
        # 提取价格
        extracted_price = self.price_extractor.extract_price(llm_response)
        
        if extracted_price is None:
            logger.warning(f"Failed to extract price from: {llm_response}")
            return False, None, "无法从回复中提取价格"
        
        # 检查是否低于底线
        if extracted_price < minimum_price:
            logger.warning(
                f"Price {extracted_price} is below minimum {minimum_price}, triggering retry"
            )
            return False, extracted_price, f"报价 ¥{extracted_price:.2f} 低于底线 ¥{minimum_price:.2f}"
        
        logger.info(f"Price {extracted_price} passed audit (minimum: {minimum_price})")
        return True, extracted_price, "审计通过"


class NegotiatorNode:
    """谈判节点 - 集成动态博弈效用函数"""
    
    def __init__(self, llm_client, local_memory, max_retries: int = 3):
        """
        初始化谈判节点
        
        Args:
            llm_client: LLM 客户端
            local_memory: 本地记忆（包含底价）
            max_retries: 最大重试次数
        """
        self.llm_client = llm_client
        self.local_memory = local_memory
        self.max_retries = max_retries
        
        self.strategy_calculator = StrategyCalculator()
        self.audit_node = AuditNode(max_retries=max_retries)
        self.negotiation_round = 0
    
    async def negotiate(
        self,
        intent: Dict[str, Any],
        merchant_id: str
    ) -> Dict[str, Any]:
        """
        执行谈判
        
        Args:
            intent: 交易意图
            merchant_id: 商家 ID
        
        Returns:
            谈判结果
        """
        self.negotiation_round += 1
        
        # 1. 从本地记忆获取底价
        base_bottom_price = await self._get_bottom_price(merchant_id, intent['item_name'])
        
        # 2. 计算动态效用
        utility = self.strategy_calculator.calculate_dynamic_utility(
            base_bottom_price=base_bottom_price,
            negotiation_round=self.negotiation_round
        )
        
        logger.info(f"Dynamic utility calculated: {utility}")
        
        # 3. 生成策略提示词
        strategy_prompt = self.strategy_calculator.get_strategy_prompt(
            utility=utility,
            base_price=base_bottom_price
        )
        
        # 4. 调用 LLM 进行谈判（带重试）
        llm_response = await self._negotiate_with_retry(
            intent=intent,
            strategy_prompt=strategy_prompt,
            minimum_price=base_bottom_price * (1 + utility.price_adjustment)
        )
        
        # 5. 审计和验证
        passed, extracted_price, audit_info = await self.audit_node.audit_and_validate(
            llm_response=llm_response,
            minimum_price=base_bottom_price * (1 + utility.price_adjustment)
        )
        
        if not passed:
            logger.error(f"Audit failed: {audit_info}")
            raise ValueError(f"Audit failed: {audit_info}")
        
        return {
            'negotiation_round': self.negotiation_round,
            'time_slot': utility.time_slot.value,
            'base_bottom_price': base_bottom_price,
            'adjusted_bottom_price': base_bottom_price * (1 + utility.price_adjustment),
            'extracted_price': extracted_price,
            'attitude_hardness': utility.attitude_hardness,
            'confidence': utility.confidence,
            'llm_response': llm_response,
            'audit_info': audit_info
        }
    
    async def _get_bottom_price(self, merchant_id: str, item_name: str) -> float:
        """从本地记忆获取底价"""
        try:
            # 查询本地记忆
            result = await self.local_memory.query(
                merchant_id=merchant_id,
                item_name=item_name
            )
            
            if result and 'bottom_price' in result:
                return result['bottom_price']
            
            # 默认底价
            return 10.0
        
        except Exception as e:
            logger.error(f"Error getting bottom price: {e}")
            return 10.0
    
    async def _negotiate_with_retry(
        self,
        intent: Dict[str, Any],
        strategy_prompt: str,
        minimum_price: float
    ) -> str:
        """
        带重试的谈判
        
        Args:
            intent: 交易意图
            strategy_prompt: 策略提示词
            minimum_price: 最低价格
        
        Returns:
            LLM 回复
        """
        for attempt in range(self.max_retries):
            try:
                logger.info(f"Negotiation attempt {attempt + 1}/{self.max_retries}")
                
                # 构建系统提示词
                system_prompt = f"""你是一个专业的商品谈判代理。
{strategy_prompt}

【回复要求】
1. 必须包含具体的报价（格式：¥XX.XX）
2. 报价不能低于底线价格
3. 保持指定的态度
4. 简洁有力，不超过 100 字
"""
                
                # 调用 LLM
                response = await self.llm_client.chat(
                    system_prompt=system_prompt,
                    user_message=f"客户想要购买 {intent['item_name']}，预算 ¥{intent['expected_price']:.2f}。请给出报价。"
                )
                
                # 验证价格
                extracted_price = PriceExtractor.extract_price(response)
                
                if extracted_price is None:
                    logger.warning(f"No price found in response: {response}")
                    continue
                
                if extracted_price < minimum_price:
                    logger.warning(
                        f"Attempt {attempt + 1}: Price {extracted_price} < minimum {minimum_price}, retrying..."
                    )
                    continue
                
                logger.info(f"Negotiation successful: ¥{extracted_price:.2f}")
                return response
            
            except Exception as e:
                logger.error(f"Negotiation attempt {attempt + 1} failed: {e}")
                if attempt == self.max_retries - 1:
                    raise
        
        raise ValueError(f"Failed to negotiate after {self.max_retries} attempts")


# 使用示例
async def example_usage():
    """使用示例"""
    from edge_box.physical_tool import OmniVisionAnalyzer
    
    # 初始化
    negotiator = NegotiatorNode(
        llm_client=None,  # 实际使用时传入真实的 LLM 客户端
        local_memory=None,  # 实际使用时传入真实的本地记忆
        max_retries=3
    )
    
    # 执行谈判
    intent = {
        'item_name': '龙虾',
        'expected_price': 15.0
    }
    
    result = await negotiator.negotiate(
        intent=intent,
        merchant_id='box-001'
    )
    
    logger.info(f"Negotiation result: {result}")
