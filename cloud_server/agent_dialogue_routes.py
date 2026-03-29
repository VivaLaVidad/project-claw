"""
Project Claw Agent 对话 API 路由
文件位置：cloud_server/agent_dialogue_routes.py
"""

from fastapi import APIRouter, WebSocket, HTTPException, Depends
from pydantic import BaseModel
import uuid
import logging
from typing import Optional, Dict
import json

from .agent_dialogue_service import (
    DialogueManager,
    ClientProfile,
    MerchantProfile,
    DialogueSession
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/a2a/dialogue", tags=["Agent Dialogue"])

# 全局对话管理器
dialogue_manager: Optional[DialogueManager] = None

def get_dialogue_manager() -> DialogueManager:
    """获取对话管理器"""
    global dialogue_manager
    if dialogue_manager is None:
        from .llm_client import get_llm_client
        dialogue_manager = DialogueManager(get_llm_client())
    return dialogue_manager


# ═══════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════

class StartDialogueRequest(BaseModel):
    """启动对话请求"""
    client_id: str
    merchant_id: str
    item_name: str
    expected_price: float
    client_profile: Dict  # ClientProfile 数据
    merchant_profile: Dict  # MerchantProfile 数据


class ContinueDialogueRequest(BaseModel):
    """继续对话请求"""
    session_id: str
    max_turns: int = 5


class DialogueResponse(BaseModel):
    """对话响应"""
    session_id: str
    status: str
    turns: list
    best_offer: Optional[Dict] = None


# ═══════════════════════════════════════════════════════════════
# HTTP 路由
# ═══════════════════════════════════════════════════════════════

@router.post("/start")
async def start_dialogue(
    request: StartDialogueRequest,
    manager: DialogueManager = Depends(get_dialogue_manager)
) -> Dict:
    """
    启动 C端Agent 和 B端Agent 之间的对话
    
    请求示例：
    {
        "client_id": "client_123",
        "merchant_id": "merchant_456",
        "item_name": "iPhone 15",
        "expected_price": 5000,
        "client_profile": {
            "price_sensitivity": 0.8,
            "time_urgency": 0.5,
            "quality_preference": 0.7
        },
        "merchant_profile": {
            "shop_name": "电子产品店",
            "pricing_strategy": "normal",
            "negotiation_style": "friendly"
        }
    }
    """
    
    try:
        # 生成会话 ID
        session_id = f"session_{uuid.uuid4().hex[:12]}"
        
        # 创建客户画像
        client_profile = ClientProfile(
            client_id=request.client_id,
            **request.client_profile
        )
        
        # 创建商家画像
        merchant_profile = MerchantProfile(
            merchant_id=request.merchant_id,
            **request.merchant_profile
        )
        
        # 启动对话
        session = await manager.start_dialogue(
            session_id=session_id,
            client_id=request.client_id,
            merchant_id=request.merchant_id,
            item_name=request.item_name,
            expected_price=request.expected_price,
            client_profile=client_profile,
            merchant_profile=merchant_profile
        )
        
        logger.info(f"Started dialogue session: {session_id}")
        
        return {
            "session_id": session_id,
            "status": session.status,
            "turns": manager.get_session_history(session_id),
            "message": "Dialogue started successfully"
        }
    
    except Exception as e:
        logger.error(f"Error starting dialogue: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/continue")
async def continue_dialogue(
    request: ContinueDialogueRequest,
    manager: DialogueManager = Depends(get_dialogue_manager)
) -> Dict:
    """
    继续对话直到达成协议
    
    请求示例：
    {
        "session_id": "session_abc123",
        "max_turns": 5
    }
    """
    
    try:
        session = await manager.continue_dialogue(
            session_id=request.session_id,
            max_turns=request.max_turns
        )
        
        logger.info(f"Continued dialogue session: {request.session_id}, status: {session.status}")
        
        return {
            "session_id": request.session_id,
            "status": session.status,
            "turns": manager.get_session_history(request.session_id),
            "best_offer": session.best_offer,
            "message": f"Dialogue {session.status}"
        }
    
    except Exception as e:
        logger.error(f"Error continuing dialogue: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}")
async def get_dialogue_session(
    session_id: str,
    manager: DialogueManager = Depends(get_dialogue_manager)
) -> Dict:
    """
    获取对话会话信息
    """
    
    try:
        session = manager.get_session(session_id)
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        return {
            "session_id": session_id,
            "client_id": session.client_id,
            "merchant_id": session.merchant_id,
            "item_name": session.item_name,
            "expected_price": session.expected_price,
            "status": session.status,
            "turns": manager.get_session_history(session_id),
            "best_offer": session.best_offer,
            "created_at": session.created_at
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting dialogue session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}/history")
async def get_dialogue_history(
    session_id: str,
    manager: DialogueManager = Depends(get_dialogue_manager)
) -> Dict:
    """
    获取对话历史
    """
    
    try:
        history = manager.get_session_history(session_id)
        
        if not history:
            raise HTTPException(status_code=404, detail="Session not found")
        
        return {
            "session_id": session_id,
            "turns": history,
            "total_turns": len(history)
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting dialogue history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════
# WebSocket 路由（实时对话）
# ═══════════════════════════════════════════════════════════════

@router.websocket("/ws/{session_id}")
async def websocket_dialogue(
    websocket: WebSocket,
    session_id: str,
    manager: DialogueManager = Depends(get_dialogue_manager)
):
    """
    WebSocket 实时对话连接
    
    客户端可以通过 WebSocket 实时接收对话更新
    """
    
    await websocket.accept()
    
    try:
        session = manager.get_session(session_id)
        
        if not session:
            await websocket.send_json({
                "type": "error",
                "message": "Session not found"
            })
            await websocket.close()
            return
        
        # 发送初始对话历史
        await websocket.send_json({
            "type": "history",
            "turns": manager.get_session_history(session_id)
        })
        
        # 监听客户端消息
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message.get("type") == "continue":
                # 继续对话
                session = await manager.continue_dialogue(
                    session_id=session_id,
                    max_turns=message.get("max_turns", 5)
                )
                
                # 发送更新
                await websocket.send_json({
                    "type": "update",
                    "status": session.status,
                    "turns": manager.get_session_history(session_id),
                    "best_offer": session.best_offer
                })
                
                if session.status != "active":
                    break
            
            elif message.get("type") == "close":
                break
    
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await websocket.send_json({
            "type": "error",
            "message": str(e)
        })
    
    finally:
        await websocket.close()


# ═══════════════════════════════════════════════════════════════
# 个性化设置路由
# ═══════════════════════════════════════════════════════════════

@router.post("/profile/client")
async def save_client_profile(
    profile: Dict,
    manager: DialogueManager = Depends(get_dialogue_manager)
) -> Dict:
    """
    保存 C端用户个性化设置
    
    请求示例：
    {
        "client_id": "client_123",
        "price_sensitivity": 0.8,
        "time_urgency": 0.5,
        "quality_preference": 0.7,
        "brand_preferences": ["Apple", "Samsung"]
    }
    """
    
    try:
        client_id = profile.get("client_id")
        
        client_profile = ClientProfile(
            client_id=client_id,
            **profile
        )
        
        manager.client_profiles[client_id] = client_profile
        
        logger.info(f"Saved client profile: {client_id}")
        
        return {
            "client_id": client_id,
            "message": "Profile saved successfully",
            "profile": profile
        }
    
    except Exception as e:
        logger.error(f"Error saving client profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/profile/merchant")
async def save_merchant_profile(
    profile: Dict,
    manager: DialogueManager = Depends(get_dialogue_manager)
) -> Dict:
    """
    保存 B端商家个性化设置
    
    请求示例：
    {
        "merchant_id": "merchant_456",
        "shop_name": "电子产品店",
        "pricing_strategy": "normal",
        "negotiation_style": "friendly",
        "service_rating": 4.8
    }
    """
    
    try:
        merchant_id = profile.get("merchant_id")
        
        merchant_profile = MerchantProfile(
            merchant_id=merchant_id,
            **profile
        )
        
        manager.merchant_profiles[merchant_id] = merchant_profile
        
        logger.info(f"Saved merchant profile: {merchant_id}")
        
        return {
            "merchant_id": merchant_id,
            "message": "Profile saved successfully",
            "profile": profile
        }
    
    except Exception as e:
        logger.error(f"Error saving merchant profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/profile/client/{client_id}")
async def get_client_profile(
    client_id: str,
    manager: DialogueManager = Depends(get_dialogue_manager)
) -> Dict:
    """
    获取 C端用户个性化设置
    """
    
    try:
        profile = manager.client_profiles.get(client_id)
        
        if not profile:
            raise HTTPException(status_code=404, detail="Client profile not found")
        
        return profile.dict()
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting client profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/profile/merchant/{merchant_id}")
async def get_merchant_profile(
    merchant_id: str,
    manager: DialogueManager = Depends(get_dialogue_manager)
) -> Dict:
    """
    获取 B端商家个性化设置
    """
    
    try:
        profile = manager.merchant_profiles.get(merchant_id)
        
        if not profile:
            raise HTTPException(status_code=404, detail="Merchant profile not found")
        
        return profile.dict()
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting merchant profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))
