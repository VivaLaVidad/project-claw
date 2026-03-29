"""Project Claw 智能模型网关 - cloud_server/model_gateway.py"""
import asyncio, logging, json, re
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import httpx

logger = logging.getLogger(__name__)

class QueryComplexity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class ModelType(str, Enum):
    LOCAL = "local"
    API = "api"

@dataclass
class ModelConfig:
    model_id: str
    model_type: ModelType
    provider: str
    base_url: str
    api_key: Optional[str] = None
    max_tokens: int = 2048
    temperature: float = 0.7
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0
    priority: int = 0
    enabled: bool = True

@dataclass
class RoutingRule:
    complexity: QueryComplexity
    primary_model: str
    fallback_models: List[str]
    max_retries: int = 3

@dataclass
class TokenUsage:
    input_tokens: int
    output_tokens: int
    total_tokens: int

class QueryComplexityAnalyzer:
    def __init__(self):
        self.simple_keywords = [r'你好|hi|hello|地址|位置|营业时间|电话|谢谢']
        self.complex_keywords = [r'议价|砍价|谈判|协商|比较|分析|评估']
    
    def analyze(self, query: str) -> QueryComplexity:
        query_lower = query.lower()
        for pattern in self.complex_keywords:
            if re.search(pattern, query_lower):
                return QueryComplexity.HIGH
        for pattern in self.simple_keywords:
            if re.search(pattern, query_lower):
                return QueryComplexity.LOW
        return QueryComplexity.MEDIUM if len(query) > 50 else QueryComplexity.LOW

class ModelRegistry:
    def __init__(self):
        self.models: Dict[str, ModelConfig] = {}
        self.routing_rules: Dict[QueryComplexity, RoutingRule] = {}
    
    def register_model(self, config: ModelConfig) -> bool:
        self.models[config.model_id] = config
        logger.info(f"✓ 模型已注册: {config.model_id}")
        return True
    
    def register_routing_rule(self, rule: RoutingRule) -> bool:
        self.routing_rules[rule.complexity] = rule
        logger.info(f"✓ 路由规则已注册: {rule.complexity.value}")
        return True
    
    def get_model(self, model_id: str) -> Optional[ModelConfig]:
        return self.models.get(model_id)
    
    def get_routing_rule(self, complexity: QueryComplexity) -> Optional[RoutingRule]:
        return self.routing_rules.get(complexity)

class ModelGateway:
    def __init__(self):
        self.registry = ModelRegistry()
        self.analyzer = QueryComplexityAnalyzer()
        self.client = httpx.AsyncClient(timeout=60.0)
        self.request_stats = {"total_requests": 0, "successful_requests": 0, "failed_requests": 0, "total_tokens": 0, "total_cost": 0.0}
    
    async def route_and_infer(self, query: str, messages: List[Dict[str, str]], tenant_id: str) -> Tuple[Dict[str, Any], TokenUsage, float]:
        try:
            complexity = self.analyzer.analyze(query)
            logger.info(f"查询复杂度: {complexity.value}")
            
            rule = self.registry.get_routing_rule(complexity)
            if not rule:
                return {"error": "No routing rule"}, TokenUsage(0, 0, 0), 0.0
            
            model_list = [rule.primary_model] + rule.fallback_models
            
            for attempt, model_id in enumerate(model_list):
                if attempt >= rule.max_retries:
                    break
                
                logger.info(f"尝试模型: {model_id}")
                result, usage, cost = await self._infer_with_model(model_id, messages, tenant_id)
                
                if result and "error" not in result:
                    self.request_stats["successful_requests"] += 1
                    self.request_stats["total_tokens"] += usage.total_tokens
                    self.request_stats["total_cost"] += cost
                    logger.info(f"✓ 推理成功: {model_id} (成本: ${cost:.4f})")
                    return result, usage, cost
                else:
                    logger.warning(f"✗ 模型失败: {model_id}")
                    await asyncio.sleep(1)
            
            self.request_stats["failed_requests"] += 1
            return {"error": "All models failed"}, TokenUsage(0, 0, 0), 0.0
        except Exception as e:
            logger.error(f"路由失败: {e}")
            self.request_stats["failed_requests"] += 1
            return {"error": str(e)}, TokenUsage(0, 0, 0), 0.0
    
    async def _infer_with_model(self, model_id: str, messages: List[Dict[str, str]], tenant_id: str) -> Tuple[Dict[str, Any], TokenUsage, float]:
        try:
            model_config = self.registry.get_model(model_id)
            if not model_config or not model_config.enabled:
                return {"error": f"Model not found: {model_id}"}, TokenUsage(0, 0, 0), 0.0
            
            if model_config.model_type == ModelType.LOCAL:
                result, usage = await self._call_local_model(model_config, messages)
            else:
                result, usage = await self._call_api_model(model_config, messages)
            
            cost = self._calculate_cost(model_config, usage)
            return result, usage, cost
        except Exception as e:
            logger.error(f"推理失败: {e}")
            return {"error": str(e)}, TokenUsage(0, 0, 0), 0.0
    
    async def _call_local_model(self, config: ModelConfig, messages: List[Dict[str, str]]) -> Tuple[Dict[str, Any], TokenUsage]:
        try:
            response = await self.client.post(f"{config.base_url}/v1/chat/completions", json={"model": config.model_id, "messages": messages, "temperature": config.temperature, "max_tokens": config.max_tokens})
            if response.status_code == 200:
                result = response.json()
                usage = TokenUsage(result.get("usage", {}).get("prompt_tokens", 0), result.get("usage", {}).get("completion_tokens", 0), result.get("usage", {}).get("total_tokens", 0))
                return result, usage
            return {"error": f"HTTP {response.status_code}"}, TokenUsage(0, 0, 0)
        except Exception as e:
            logger.error(f"本地模型失败: {e}")
            return {"error": str(e)}, TokenUsage(0, 0, 0)
    
    async def _call_api_model(self, config: ModelConfig, messages: List[Dict[str, str]]) -> Tuple[Dict[str, Any], TokenUsage]:
        try:
            headers = {"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"}
            response = await self.client.post(f"{config.base_url}/v1/chat/completions", headers=headers, json={"model": config.model_id, "messages": messages, "temperature": config.temperature, "max_tokens": config.max_tokens}, timeout=30.0)
            if response.status_code == 200:
                result = response.json()
                usage = TokenUsage(result.get("usage", {}).get("prompt_tokens", 0), result.get("usage", {}).get("completion_tokens", 0), result.get("usage", {}).get("total_tokens", 0))
                return result, usage
            elif response.status_code >= 500:
                logger.error(f"API 服务器错误: {response.status_code}")
            return {"error": f"HTTP {response.status_code}"}, TokenUsage(0, 0, 0)
        except asyncio.TimeoutError:
            logger.error("API 请求超时")
            return {"error": "Timeout"}, TokenUsage(0, 0, 0)
        except Exception as e:
            logger.error(f"API 模型失败: {e}")
            return {"error": str(e)}, TokenUsage(0, 0, 0)
    
    def _calculate_cost(self, config: ModelConfig, usage: TokenUsage) -> float:
        return (usage.input_tokens / 1000) * config.cost_per_1k_input + (usage.output_tokens / 1000) * config.cost_per_1k_output
    
    def get_stats(self) -> Dict[str, Any]:
        return {**self.request_stats, "avg_cost": self.request_stats["total_cost"] / max(self.request_stats["successful_requests"], 1)}
    
    async def close(self):
        await self.client.aclose()
        logger.info("✓ 模型网关已关闭")

_model_gateway: Optional[ModelGateway] = None

def get_model_gateway() -> ModelGateway:
    global _model_gateway
    if _model_gateway is None:
        _model_gateway = ModelGateway()
    return _model_gateway

async def initialize_model_gateway() -> ModelGateway:
    global _model_gateway
    _model_gateway = ModelGateway()
    
    _model_gateway.registry.register_model(ModelConfig(model_id="qwen-1.8b", model_type=ModelType.LOCAL, provider="qwen", base_url="http://localhost:8000", cost_per_1k_input=0.0, cost_per_1k_output=0.0, priority=1))
    _model_gateway.registry.register_model(ModelConfig(model_id="deepseek-chat", model_type=ModelType.API, provider="deepseek", base_url="https://api.deepseek.com", api_key="your-key", cost_per_1k_input=0.0014, cost_per_1k_output=0.0042, priority=2))
    _model_gateway.registry.register_model(ModelConfig(model_id="claude-3.5-sonnet", model_type=ModelType.API, provider="anthropic", base_url="https://api.anthropic.com", api_key="your-key", cost_per_1k_input=0.003, cost_per_1k_output=0.015, priority=3))
    
    _model_gateway.registry.register_routing_rule(RoutingRule(QueryComplexity.LOW, "qwen-1.8b", ["deepseek-chat", "claude-3.5-sonnet"]))
    _model_gateway.registry.register_routing_rule(RoutingRule(QueryComplexity.HIGH, "deepseek-chat", ["claude-3.5-sonnet", "qwen-1.8b"]))
    _model_gateway.registry.register_routing_rule(RoutingRule(QueryComplexity.MEDIUM, "qwen-1.8b", ["deepseek-chat"]))
    
    logger.info("✓ 模型网关已初始化")
    return _model_gateway
