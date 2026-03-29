"""Project Claw 语音流 WebSocket 路由 - cloud_server/audio_websocket.py"""
import asyncio, logging, json, uuid
from typing import Dict, Set
from fastapi import WebSocket, WebSocketDisconnect, APIRouter
from .audio_streaming import AudioStreamManager, AudioStreamConfig, LLMAudioInterface

logger = logging.getLogger(__name__)
router = APIRouter()

class AudioWebSocketManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.stream_manager = AudioStreamManager(AudioStreamConfig())
        self.llm_interface = None
    
    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        self.active_connections[session_id] = websocket
        logger.info(f"WebSocket 连接: {session_id}")
    
    async def disconnect(self, session_id: str):
        if session_id in self.active_connections:
            del self.active_connections[session_id]
            await self.stream_manager.close_session(session_id)
            logger.info(f"WebSocket 断开: {session_id}")
    
    async def broadcast_audio(self, session_id: str, audio_data: bytes):
        if session_id in self.active_connections:
            try:
                await self.active_connections[session_id].send_bytes(audio_data)
            except Exception as e:
                logger.error(f"发送音频失败: {e}")

manager = AudioWebSocketManager()

@router.websocket("/ws/audio/{session_id}")
async def websocket_audio_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket 音频流端点"""
    await manager.connect(websocket, session_id)
    
    try:
        # 创建音频流会话
        await manager.stream_manager.create_session(
            session_id,
            manager.llm_interface,
            "你是一个友好的销售助手，帮助客户了解产品并完成交易。"
        )
        
        while True:
            # 接收客户端音频
            data = await websocket.receive_bytes()
            
            if not data:
                break
            
            # 添加音频块
            await manager.stream_manager.add_audio_chunk(session_id, data)
            
            # 检查是否是最后一块
            message = await websocket.receive_text()
            msg_data = json.loads(message)
            
            if msg_data.get("is_final"):
                # 处理音频流
                async for audio_chunk, metadata in manager.stream_manager.process_audio_stream(session_id):
                    # 发送音频块给客户端
                    await manager.broadcast_audio(session_id, audio_chunk)
                    
                    # 发送元数据
                    await websocket.send_text(json.dumps({
                        "type": "audio_metadata",
                        "metadata": metadata
                    }))
    
    except WebSocketDisconnect:
        await manager.disconnect(session_id)
    except Exception as e:
        logger.error(f"WebSocket 错误: {e}")
        await manager.disconnect(session_id)

@router.get("/audio/status/{session_id}")
async def get_audio_status(session_id: str):
    """获取音频流状态"""
    status = manager.stream_manager.get_session_status(session_id)
    if status:
        return {"success": True, "data": status}
    return {"success": False, "message": "会话不存在"}

@router.post("/audio/close/{session_id}")
async def close_audio_session(session_id: str):
    """关闭音频流会话"""
    await manager.stream_manager.close_session(session_id)
    return {"success": True, "message": "会话已关闭"}
