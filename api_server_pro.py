"""
api_server_pro.py - Project Claw 工业级 API 服务
包含：熔断器 + 指标上报 + ChromaDB 检索
"""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import asyncio
import json
import logging
from typing import Dict, List
from datetime import datetime, timedelta
from collections import deque
import time
from enum import Enum

# 导入业务模块
from run_business import build_graph, BusinessState, InventoryAgent, BossAgent, FeishuSync
from lobster_tool import LobsterPhysicalTool

# 可选：ChromaDB（如果未安装会自动跳过）
try:
    import chromadb
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    logging.warning("⚠️ ChromaDB 未安装，检索功能将被禁用")

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="Project Claw Pro", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== 熔断器（Circuit Breaker） ====================

class CircuitState(str, Enum):
    CLOSED = "closed"      # 正常
    OPEN = "open"          # 熔断
    HALF_OPEN = "half_open"  # 半开


class CircuitBreaker:
    """熔断器：防止级联故障"""
    
    def __init__(self, failure_threshold: int = 5, timeout_sec: int = 60):
        self.failure_threshold = failure_threshold
        self.timeout_sec = timeout_sec
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitState.CLOSED

    def call(self, func, *args, **kwargs):
        """执行函数，如果熔断则抛出异常"""
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time > self.timeout_sec:
                self.state = CircuitState.HALF_OPEN
                logger.info("🔄 熔断器进入半开状态")
            else:
                raise Exception("❌ 熔断器已打开，服务暂时不可用")
        
        try:
            result = func(*args, **kwargs)
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                logger.info("✅ 熔断器已关闭")
            return result
        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
                logger.error(f"🔴 熔断器已打开（失败 {self.failure_count} 次）")
            
            raise e


# ==================== 指标收集器（Metrics） ====================

class MetricsCollector:
    """收集系统指标"""
    
    def __init__(self, window_size: int = 100):
        self.window_size = window_size
        self.requests = deque(maxlen=window_size)
        self.errors = deque(maxlen=window_size)
        self.latencies = deque(maxlen=window_size)

    def record_request(self, endpoint: str, status: str, latency_ms: float):
        """记录请求"""
        self.requests.append({
            "endpoint": endpoint,
            "status": status,
            "timestamp": datetime.now().isoformat(),
            "latency_ms": latency_ms
        })
        
        if status == "error":
            self.errors.append({"endpoint": endpoint, "timestamp": datetime.now().isoformat()})
        
        self.latencies.append(latency_ms)

    def get_stats(self) -> dict:
        """获取统计信息"""
        if not self.requests:
            return {"total": 0, "error_rate": 0, "avg_latency": 0}
        
        total = len(self.requests)
        errors = len(self.errors)
        error_rate = (errors / total * 100) if total > 0 else 0
        avg_latency = sum(self.latencies) / len(self.latencies) if self.latencies else 0
        
        return {
            "total_requests": total,
            "total_errors": errors,
            "error_rate": f"{error_rate:.2f}%",
            "avg_latency_ms": f"{avg_latency:.2f}",
            "p95_latency_ms": f"{sorted(self.latencies)[int(len(self.latencies)*0.95)] if self.latencies else 0:.2f}"
        }


# ==================== ChromaDB 检索节点 ====================

class ChromaDBRetriever:
    """ChromaDB 向量检索：存储和检索对话历史"""
    
    def __init__(self, collection_name: str = "lobster_conversations"):
        if not CHROMA_AVAILABLE:
            logger.warning("⚠️ ChromaDB 不可用")
            self.client = None
            return
        
        try:
            self.client = chromadb.Client()
            self.collection = self.client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"}
            )
            logger.info("✅ ChromaDB 已初始化")
        except Exception as e:
            logger.error(f"❌ ChromaDB 初始化失败: {e}")
            self.client = None

    def add_conversation(self, user_msg: str, bot_reply: str, metadata: dict = None):
        """添加对话到向量库"""
        if not self.client:
            return
        
        try:
            doc_id = f"conv_{int(time.time() * 1000)}"
            self.collection.add(
                ids=[doc_id],
                documents=[f"用户: {user_msg}\n龙虾: {bot_reply}"],
                metadatas=[metadata or {"timestamp": datetime.now().isoformat()}]
            )
            logger.info(f"✅ 对话已保存到 ChromaDB: {doc_id}")
        except Exception as e:
            logger.error(f"❌ ChromaDB 保存失败: {e}")

    def search_similar(self, query: str, top_k: int = 3) -> list:
        """搜索相似对话"""
        if not self.client:
            return []
        
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=top_k
            )
            return results.get("documents", [[]])[0]
        except Exception as e:
            logger.error(f"❌ ChromaDB 搜索失败: {e}")
            return []


# ==================== 全局实例 ====================

metrics = MetricsCollector()
circuit_breaker = CircuitBreaker(failure_threshold=5, timeout_sec=60)
chroma_retriever = ChromaDBRetriever()
manager = None  # WebSocket 连接管理器


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"✅ WebSocket 连接成功")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info(f"❌ WebSocket 断开连接")

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"❌ 广播失败: {e}")


manager = ConnectionManager()


# ==================== REST API 端点 ====================

@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "ok",
        "circuit_breaker": circuit_breaker.state,
        "timestamp": datetime.now().isoformat()
    }


@app.get("/metrics")
async def get_metrics():
    """获取系统指标"""
    return {
        "status": "success",
        "metrics": metrics.get_stats(),
        "timestamp": datetime.now().isoformat()
    }


@app.get("/search")
async def search_conversations(query: str, top_k: int = 3):
    """搜索相似对话"""
    try:
        start_time = time.time()
        results = chroma_retriever.search_similar(query, top_k)
        latency = (time.time() - start_time) * 1000
        
        metrics.record_request("/search", "success", latency)
        
        return {
            "status": "success",
            "query": query,
            "results": results,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"❌ 搜索失败: {e}")
        metrics.record_request("/search", "error", 0)
        return {"status": "error", "message": str(e)}


@app.post("/run-agent")
async def run_agent(request: dict = None):
    """运行多智能体（带熔断器保护）"""
    try:
        start_time = time.time()
        
        def execute_agent():
            graph = build_graph()
            initial_state = {
                "user_message": None,
                "inventory_check": None,
                "boss_reply": None,
                "send_success": False,
                "error": None
            }
            return graph.invoke(initial_state)
        
        result = circuit_breaker.call(execute_agent)
        latency = (time.time() - start_time) * 1000
        
        metrics.record_request("/run-agent", "success", latency)
        
        # 保存到 ChromaDB
        if result.get("user_message") and result.get("boss_reply"):
            chroma_retriever.add_conversation(
                result["user_message"],
                result["boss_reply"],
                {"send_success": result.get("send_success")}
            )
        
        return {
            "status": "success",
            "result": result,
            "latency_ms": f"{latency:.2f}",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"❌ Agent 执行失败: {e}")
        metrics.record_request("/run-agent", "error", 0)
        return {"status": "error", "message": str(e)}


# ==================== WebSocket ====================

@app.websocket("/ws/agent-stream")
async def websocket_agent_stream(websocket: WebSocket):
    """WebSocket 实时推送"""
    await manager.connect(websocket)
    
    try:
        while True:
            data = await websocket.receive_text()
            command = json.loads(data)
            
            if command.get("action") == "start_agent":
                try:
                    result = circuit_breaker.call(
                        lambda: build_graph().invoke({
                            "user_message": None,
                            "inventory_check": None,
                            "boss_reply": None,
                            "send_success": False,
                            "error": None
                        })
                    )
                    
                    await websocket.send_json({
                        "type": "agent_result",
                        "result": result,
                        "timestamp": datetime.now().isoformat()
                    })
                except Exception as e:
                    await websocket.send_json({
                        "type": "agent_error",
                        "error": str(e),
                        "timestamp": datetime.now().isoformat()
                    })
    
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.on_event("startup")
async def startup_event():
    logger.info("=" * 70)
    logger.info("🦞 Project Claw Pro v2.0 已启动")
    logger.info("=" * 70)
    logger.info("📍 API 文档: http://localhost:8000/docs")
    logger.info("📍 指标: http://localhost:8000/metrics")
    logger.info("📍 搜索: http://localhost:8000/search?query=...")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
