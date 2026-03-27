"""
api_server.py - Project Claw 后端 API 服务
集成 LangGraph 多智能体 + FastAPI + WebSocket 实时推送
"""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Dict, List
from datetime import datetime
from dotenv import load_dotenv
from run_business import build_graph, BusinessState, InventoryAgent, BossAgent, FeishuSync
from lobster_tool import LobsterPhysicalTool
from settings import load_settings

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)
load_dotenv()
settings = load_settings()

@asynccontextmanager
async def lifespan(_: FastAPI):
    """应用生命周期钩子（替代已弃用的 on_event）"""
    logger.info("=" * 70)
    logger.info("🦞 Project Claw API 服务已启动")
    logger.info("=" * 70)
    logger.info("📍 API 文档: http://localhost:8000/docs")
    logger.info("📍 WebSocket: ws://localhost:8000/ws/agent-stream")
    yield
    logger.info("🛑 Project Claw API 服务已关闭")


# FastAPI 应用
app = FastAPI(title="Project Claw API", version="1.0.0", lifespan=lifespan)

# CORS 配置（允许 OpenMAIC 前端跨域访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# WebSocket 连接管理
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"✅ WebSocket 连接成功，当前连接数: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info(f"❌ WebSocket 断开连接，当前连接数: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """广播消息到所有连接的客户端"""
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"❌ 广播消息失败: {e}")


manager = ConnectionManager()


# ==================== REST API 端点 ====================

@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.get("/openmaic/status")
async def openmaic_status():
    """OpenMAIC integration status"""
    return {
        "enabled": settings.openmaic_enabled,
        "mode": "langgraph-business-loop",
        "base_url": settings.openmaic_base_url,
        "model": settings.openmaic_model,
        "agent_ids": settings.openmaic_agent_ids,
        "timestamp": datetime.now().isoformat()
    }


@app.get("/brain/status")
async def brain_status():
    """Current cognition pipeline status"""
    return {
        "primary_brain": "openmaic" if settings.openmaic_enabled else "deepseek",
        "fallback_brain": "deepseek",
        "openmaic": {
            "enabled": settings.openmaic_enabled,
            "base_url": settings.openmaic_base_url,
            "model": settings.openmaic_model,
            "agent_ids": settings.openmaic_agent_ids,
        },
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/inventory")
async def get_inventory():
    """获取库存列表"""
    try:
        agent = InventoryAgent()
        return {
            "status": "success",
            "inventory": agent.inventory,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"❌ 获取库存失败: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/generate-reply")
async def generate_reply(request: dict):
    """生成回复"""
    try:
        user_message = request.get("message", "")
        inventory_info = request.get("inventory", {})
        
        if not user_message:
            return {"status": "error", "message": "消息不能为空"}
        
        boss_agent = BossAgent()
        reply = boss_agent.generate_reply(user_message, inventory_info)
        
        return {
            "status": "success",
            "user_message": user_message,
            "reply": reply,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"❌ 生成回复失败: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/send-message")
async def send_message(request: dict):
    """发送消息"""
    try:
        text = request.get("text", "")
        
        if not text:
            return {"status": "error", "message": "文本不能为空"}
        
        tool = LobsterPhysicalTool()
        success = tool.send_wechat_message(text)
        
        # 同步到飞书
        if success:
            user_message = request.get("user_message", "")
            feishu = FeishuSync()
            feishu.sync_record(user_message, text)
        
        return {
            "status": "success" if success else "failed",
            "message": text,
            "sent": success,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"❌ 发送消息失败: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/run-agent")
async def run_agent(request: dict = None):
    """运行一次完整的多智能体流程"""
    try:
        graph = build_graph()
        
        initial_state = {
            "user_message": None,
            "inventory_check": None,
            "boss_reply": None,
            "send_success": False,
            "error": None
        }
        
        result = graph.invoke(initial_state)
        
        return {
            "status": "success",
            "result": result,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"❌ 运行 Agent 失败: {e}")
        return {"status": "error", "message": str(e)}


# ==================== WebSocket 实时推送 ====================

@app.websocket("/ws/agent-stream")
async def websocket_agent_stream(websocket: WebSocket):
    """WebSocket 端点：实时推送 Agent 执行日志"""
    await manager.connect(websocket)
    
    try:
        while True:
            # 接收前端的命令
            data = await websocket.receive_text()
            command = json.loads(data)
            
            logger.info(f"📨 收到命令: {command}")
            
            if command.get("action") == "start_agent":
                # 运行多智能体
                await run_agent_with_stream(websocket)
            
            elif command.get("action") == "get_message":
                # 获取最新消息
                tool = LobsterPhysicalTool()
                message = tool.get_latest_message()
                
                await websocket.send_json({
                    "type": "message",
                    "content": message,
                    "timestamp": datetime.now().isoformat()
                })
            
            elif command.get("action") == "send_message":
                # 发送消息
                text = command.get("text", "")
                tool = LobsterPhysicalTool()
                success = tool.send_wechat_message(text)
                
                await websocket.send_json({
                    "type": "send_result",
                    "success": success,
                    "text": text,
                    "timestamp": datetime.now().isoformat()
                })
    
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("❌ WebSocket 连接已断开")
    except Exception as e:
        logger.error(f"❌ WebSocket 异常: {e}")
        manager.disconnect(websocket)


async def run_agent_with_stream(websocket: WebSocket):
    """运行 Agent 并实时推送日志"""
    try:
        graph = build_graph()
        
        initial_state = {
            "user_message": None,
            "inventory_check": None,
            "boss_reply": None,
            "send_success": False,
            "error": None
        }
        
        # 推送开始事件
        await websocket.send_json({
            "type": "agent_start",
            "timestamp": datetime.now().isoformat()
        })
        
        # 执行 Agent
        result = graph.invoke(initial_state)
        
        # 推送结果
        await websocket.send_json({
            "type": "agent_result",
            "result": result,
            "timestamp": datetime.now().isoformat()
        })
        
        # 推送完成事件
        await websocket.send_json({
            "type": "agent_complete",
            "success": result.get("send_success", False),
            "timestamp": datetime.now().isoformat()
        })
    
    except Exception as e:
        logger.error(f"❌ Agent 执行失败: {e}")
        await websocket.send_json({
            "type": "agent_error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
