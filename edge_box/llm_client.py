"""Project Claw 多租户 LLM 客户端 - edge_box/llm_client.py"""
import asyncio, logging, json, time
from typing import Dict, List, Optional, Any, AsyncGenerator
from dataclasses import dataclass
from enum import Enum
import httpx

logger = logging.getLogger(__name__)

class InferenceEngine(str, Enum):
    VLLM = "vllm"
    OLLAMA = "ollama"
    OPENAI = "openai"

@dataclass
class LoRAAdapter:
    adapter_id: str
    industry: str
    version: str
    base_model: str
    enabled: bool = True
    priority: int = 0

@dataclass
class TenantConfig:
    tenant_id: str
    industry: str
    adapter_id: str
    system_prompt: str
    temperature: float = 0.7
    max_tokens: int = 2048
    top_p: float = 0.9

@dataclass
class InferenceRequest:
    tenant_id: str
    messages: List[Dict[str, str]]
    adapter_id: str
    temperature: float = 0.7
    max_tokens: int = 2048
    stream: bool = False

class LoRARegistry:
    """LoRA 适配器注册表"""
    
    def __init__(self):
        self.adapters: Dict[str, LoRAAdapter] = {}
        self.tenant_adapters: Dict[str, str] = {}  # tenant_id -> adapter_id
    
    def register_adapter(self, adapter: LoRAAdapter) -> bool:
        """注册 LoRA 适配器"""
        try:
            self.adapters[adapter.adapter_id] = adapter
            logger.info(f"✓ LoRA 适配器已注册: {adapter.adapter_id} ({adapter.industry})")
            return True
        except Exception as e:
            logger.error(f"注册 LoRA 适配器失败: {e}")
            return False
    
    def bind_tenant_adapter(self, tenant_id: str, adapter_id: str) -> bool:
        """绑定租户到 LoRA 适配器"""
        try:
            if adapter_id not in self.adapters:
                logger.error(f"适配器不存在: {adapter_id}")
                return False
            
            self.tenant_adapters[tenant_id] = adapter_id
            logger.info(f"✓ 租户已绑定: {tenant_id} -> {adapter_id}")
            return True
        except Exception as e:
            logger.error(f"绑定租户适配器失败: {e}")
            return False
    
    def get_adapter(self, adapter_id: str) -> Optional[LoRAAdapter]:
        """获取 LoRA 适配器"""
        return self.adapters.get(adapter_id)
    
    def get_tenant_adapter(self, tenant_id: str) -> Optional[LoRAAdapter]:
        """获取租户的 LoRA 适配器"""
        adapter_id = self.tenant_adapters.get(tenant_id)
        if adapter_id:
            return self.adapters.get(adapter_id)
        return None
    
    def list_adapters(self) -> List[LoRAAdapter]:
        """列出所有适配器"""
        return list(self.adapters.values())

class MultiTenantLLMClient:
    """多租户 LLM 客户端"""
    
    def __init__(
        self,
        engine: InferenceEngine = InferenceEngine.VLLM,
        base_url: str = "http://localhost:8000",
        base_model: str = "qwen-7b",
        max_concurrent_requests: int = 10
    ):
        self.engine = engine
        self.base_url = base_url
        self.base_model = base_model
        self.client = httpx.AsyncClient(timeout=300.0)
        
        # 并发控制
        self.semaphore = asyncio.Semaphore(max_concurrent_requests)
        self.max_concurrent_requests = max_concurrent_requests
        
        # LoRA 注册表
        self.lora_registry = LoRARegistry()
        
        # 租户配置
        self.tenant_configs: Dict[str, TenantConfig] = {}
        
        # 请求统计
        self.request_stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_tokens": 0
        }
    
    def register_tenant(self, config: TenantConfig) -> bool:
        """注册租户"""
        try:
            self.tenant_configs[config.tenant_id] = config
            logger.info(f"✓ 租户已注册: {config.tenant_id} ({config.industry})")
            return True
        except Exception as e:
            logger.error(f"注册租户失败: {e}")
            return False
    
    def _build_model_identifier(self, adapter_id: str) -> str:
        """构建模型标识符"""
        if self.engine == InferenceEngine.VLLM:
            # vLLM 格式: base_model:lora_id
            return f"{self.base_model}:{adapter_id}"
        elif self.engine == InferenceEngine.OLLAMA:
            # Ollama 格式: base_model:lora_id
            return f"{self.base_model}:{adapter_id}"
        else:
            # OpenAI 格式
            return f"{self.base_model}-{adapter_id}"
    
    async def _make_request(
        self,
        request: InferenceRequest,
        system_prompt: str
    ) -> Dict[str, Any]:
        """发送推理请求"""
        
        # 构建消息
        messages = [
            {"role": "system", "content": system_prompt},
            *request.messages
        ]
        
        # 构建模型标识符
        model_identifier = self._build_model_identifier(request.adapter_id)
        
        # 构建请求体
        payload = {
            "model": model_identifier,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": request.stream
        }
        
        logger.info(f"发送推理请求: {request.tenant_id} -> {model_identifier}")
        
        try:
            if self.engine == InferenceEngine.VLLM:
                response = await self.client.post(
                    f"{self.base_url}/v1/chat/completions",
                    json=payload
                )
            elif self.engine == InferenceEngine.OLLAMA:
                response = await self.client.post(
                    f"{self.base_url}/api/chat",
                    json=payload
                )
            else:
                response = await self.client.post(
                    f"{self.base_url}/v1/chat/completions",
                    json=payload
                )
            
            if response.status_code == 200:
                result = response.json()
                self.request_stats["successful_requests"] += 1
                
                # 统计 token 使用
                if "usage" in result:
                    self.request_stats["total_tokens"] += result["usage"].get("total_tokens", 0)
                
                logger.info(f"✓ 推理成功: {request.tenant_id}")
                return result
            else:
                logger.error(f"推理失败: {response.status_code} {response.text}")
                self.request_stats["failed_requests"] += 1
                return {"error": f"HTTP {response.status_code}"}
        
        except Exception as e:
            logger.error(f"推理异常: {e}")
            self.request_stats["failed_requests"] += 1
            return {"error": str(e)}
    
    async def infer(
        self,
        request: InferenceRequest,
        system_prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        """执行推理（带并发控制）"""
        
        # 获取租户配置
        tenant_config = self.tenant_configs.get(request.tenant_id)
        if not tenant_config:
            logger.error(f"租户不存在: {request.tenant_id}")
            return {"error": "Tenant not found"}
        
        # 使用租户的系统提示词
        if system_prompt is None:
            system_prompt = tenant_config.system_prompt
        
        # 使用信号量控制并发
        async with self.semaphore:
            self.request_stats["total_requests"] += 1
            
            # 记录当前并发数
            current_concurrent = self.max_concurrent_requests - self.semaphore._value
            logger.info(f"当前并发请求数: {current_concurrent}/{self.max_concurrent_requests}")
            
            return await self._make_request(request, system_prompt)
    
    async def infer_stream(
        self,
        request: InferenceRequest,
        system_prompt: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """执行流式推理"""
        
        # 获取租户配置
        tenant_config = self.tenant_configs.get(request.tenant_id)
        if not tenant_config:
            logger.error(f"租户不存在: {request.tenant_id}")
            return
        
        # 使用租户的系统提示词
        if system_prompt is None:
            system_prompt = tenant_config.system_prompt
        
        # 构建消息
        messages = [
            {"role": "system", "content": system_prompt},
            *request.messages
        ]
        
        # 构建模型标识符
        model_identifier = self._build_model_identifier(request.adapter_id)
        
        # 构建请求体
        payload = {
            "model": model_identifier,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": True
        }
        
        async with self.semaphore:
            self.request_stats["total_requests"] += 1
            
            try:
                if self.engine == InferenceEngine.VLLM:
                    url = f"{self.base_url}/v1/chat/completions"
                elif self.engine == InferenceEngine.OLLAMA:
                    url = f"{self.base_url}/api/chat"
                else:
                    url = f"{self.base_url}/v1/chat/completions"
                
                async with self.client.stream("POST", url, json=payload) as response:
                    if response.status_code == 200:
                        async for line in response.aiter_lines():
                            if line.startswith("data: "):
                                data = line[6:]
                                if data == "[DONE]":
                                    break
                                try:
                                    chunk = json.loads(data)
                                    if "choices" in chunk:
                                        delta = chunk["choices"][0].get("delta", {})
                                        if "content" in delta:
                                            yield delta["content"]
                                except json.JSONDecodeError:
                                    continue
                        
                        self.request_stats["successful_requests"] += 1
                    else:
                        logger.error(f"流式推理失败: {response.status_code}")
                        self.request_stats["failed_requests"] += 1
            
            except Exception as e:
                logger.error(f"流式推理异常: {e}")
                self.request_stats["failed_requests"] += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self.request_stats,
            "current_concurrent_limit": self.max_concurrent_requests,
            "available_adapters": len(self.lora_registry.adapters),
            "registered_tenants": len(self.tenant_configs)
        }
    
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            if self.engine == InferenceEngine.VLLM:
                response = await self.client.get(f"{self.base_url}/health")
            elif self.engine == InferenceEngine.OLLAMA:
                response = await self.client.get(f"{self.base_url}/api/tags")
            else:
                response = await self.client.get(f"{self.base_url}/health")
            
            return response.status_code == 200
        except Exception as e:
            logger.error(f"健康检查失败: {e}")
            return False
    
    async def close(self):
        """关闭客户端"""
        await self.client.aclose()
        logger.info("✓ LLM 客户端已关闭")

# 全局客户端实例
_llm_client: Optional[MultiTenantLLMClient] = None

def get_llm_client() -> MultiTenantLLMClient:
    """获取全局 LLM 客户端"""
    global _llm_client
    if _llm_client is None:
        _llm_client = MultiTenantLLMClient(
            engine=InferenceEngine.VLLM,
            base_url="http://localhost:8000",
            base_model="qwen-7b",
            max_concurrent_requests=10
        )
    return _llm_client

async def initialize_llm_client(
    engine: InferenceEngine = InferenceEngine.VLLM,
    base_url: str = "http://localhost:8000",
    base_model: str = "qwen-7b",
    max_concurrent_requests: int = 10
) -> MultiTenantLLMClient:
    """初始化 LLM 客户端"""
    global _llm_client
    _llm_client = MultiTenantLLMClient(
        engine=engine,
        base_url=base_url,
        base_model=base_model,
        max_concurrent_requests=max_concurrent_requests
    )
    
    # 健康检查
    is_healthy = await _llm_client.health_check()
    if is_healthy:
        logger.info("✓ LLM 客户端已初始化并通过健康检查")
    else:
        logger.warning("⚠ LLM 客户端初始化成功，但健康检查失败")
    
    return _llm_client
