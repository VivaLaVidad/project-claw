"""
Project Claw 工业级 API 路由修复
文件位置：cloud_server/api_routes_fix.py
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import logging

from .industrial_fix import (
    MerchantDataManager,
    DialogueDataManager,
    StatisticsManager,
    get_merchants_api,
    get_merchant_api,
    get_dashboard_stats_api,
    get_dialogues_api
)

logger = logging.getLogger(__name__)

# 创建路由
router = APIRouter(prefix="/api/v1", tags=["API v1"])


# ═══════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════

class MerchantResponse(BaseModel):
    """商家响应模型"""
    merchant_id: str
    shop_name: str
    category: str
    rating: float
    sales: int
    status: str
    location: str
    description: str


class DialogueRequest(BaseModel):
    """对话请求模型"""
    client_id: str
    merchant_id: str
    item_name: str
    expected_price: float


class MessageRequest(BaseModel):
    """消息请求模型"""
    session_id: str
    speaker: str
    text: str


# ═══════════════════════════════════════════════════════════════
# 商家相关 API
# ═══════════════════════════════════════════════════════════════

@router.get("/merchants", summary="获取所有在线商家")
async def get_merchants():
    """
    获取所有在线商家列表
    
    返回：
    - merchants: 商家列表
    - total: 商家总数
    """
    try:
        result = await get_merchants_api()
        return result
    except Exception as e:
        logger.error(f"获取商家列表失败: {e}")
        raise HTTPException(status_code=500, detail="获取商家列表失败")


@router.get("/merchants/{merchant_id}", summary="获取单个商家信息")
async def get_merchant(merchant_id: str):
    """
    获取单个商家的详细信息
    
    参数：
    - merchant_id: 商家 ID
    
    返回：
    - 商家详细信息
    """
    try:
        result = await get_merchant_api(merchant_id)
        if result["code"] != "0000":
            raise HTTPException(status_code=404, detail="商家不存在")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取商家信息失败: {e}")
        raise HTTPException(status_code=500, detail="获取商家信息失败")


@router.get("/merchants/category/{category}", summary="按分类获取商家")
async def get_merchants_by_category(category: str):
    """
    按分类获取商家列表
    
    参数：
    - category: 分类（electronics, clothing, food, home, beauty）
    
    返回：
    - merchants: 商家列表
    - total: 商家总数
    """
    try:
        merchants = await MerchantDataManager.get_merchants_by_category(category)
        return {
            "code": "0000",
            "message": "success",
            "data": {
                "merchants": merchants,
                "total": len(merchants),
                "category": category
            }
        }
    except Exception as e:
        logger.error(f"按分类获取商家失败: {e}")
        raise HTTPException(status_code=500, detail="按分类获取商家失败")


# ═══════════════════════════════════════════════════════════════
# 对话相关 API
# ═══════════════════════════════════════════════════════════════

@router.post("/dialogues", summary="创建对话会话")
async def create_dialogue(request: DialogueRequest):
    """
    创建新的对话会话
    
    参数：
    - client_id: 用户 ID
    - merchant_id: 商家 ID
    - item_name: 商品名称
    - expected_price: 期望价格
    
    返回：
    - session_id: 会话 ID
    - status: 会话状态
    """
    try:
        import uuid
        session_id = str(uuid.uuid4())
        
        dialogue = await DialogueDataManager.create_dialogue(
            session_id=session_id,
            client_id=request.client_id,
            merchant_id=request.merchant_id,
            item_name=request.item_name,
            expected_price=request.expected_price
        )
        
        return {
            "code": "0000",
            "message": "success",
            "data": dialogue
        }
    except Exception as e:
        logger.error(f"创建对话失败: {e}")
        raise HTTPException(status_code=500, detail="创建对话失败")


@router.get("/dialogues/{session_id}", summary="获取对话会话")
async def get_dialogue(session_id: str):
    """
    获取对话会话详情
    
    参数：
    - session_id: 会话 ID
    
    返回：
    - 对话会话详情
    """
    try:
        dialogue = await DialogueDataManager.get_dialogue(session_id)
        if not dialogue:
            raise HTTPException(status_code=404, detail="对话会话不存在")
        
        return {
            "code": "0000",
            "message": "success",
            "data": dialogue
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取对话失败: {e}")
        raise HTTPException(status_code=500, detail="获取对话失败")


@router.get("/dialogues", summary="获取所有对话")
async def get_all_dialogues():
    """
    获取所有对话会话列表
    
    返回：
    - dialogues: 对话列表
    - total: 对话总数
    """
    try:
        result = await get_dialogues_api()
        return result
    except Exception as e:
        logger.error(f"获取所有对话失败: {e}")
        raise HTTPException(status_code=500, detail="获取所有对话失败")


@router.post("/dialogues/{session_id}/messages", summary="添加对话消息")
async def add_message(session_id: str, request: MessageRequest):
    """
    添加对话消息
    
    参数：
    - session_id: 会话 ID
    - speaker: 发言人（client, merchant, agent）
    - text: 消息内容
    
    返回：
    - success: 是否成功
    """
    try:
        success = await DialogueDataManager.add_message(
            session_id=session_id,
            speaker=request.speaker,
            text=request.text
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="对话会话不存在")
        
        return {
            "code": "0000",
            "message": "success",
            "data": {"success": True}
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"添加消息失败: {e}")
        raise HTTPException(status_code=500, detail="添加消息失败")


# ═══════════════════════════════════════════════════════════════
# 统计相关 API
# ═══════════════════════════════════════════════════════════════

@router.get("/statistics/dashboard", summary="获取仪表板统计")
async def get_dashboard_stats():
    """
    获取仪表板统计数据
    
    返回：
    - total_merchants: 商家总数
    - online_merchants: 在线商家数
    - total_dialogues: 对话总数
    - active_dialogues: 活跃对话数
    - completed_dialogues: 已完成对话数
    - total_sales: 总销售额
    - avg_rating: 平均评分
    """
    try:
        result = await get_dashboard_stats_api()
        return result
    except Exception as e:
        logger.error(f"获取仪表板统计失败: {e}")
        raise HTTPException(status_code=500, detail="获取仪表板统计失败")


@router.get("/statistics/merchants/{merchant_id}", summary="获取商家统计")
async def get_merchant_stats(merchant_id: str):
    """
    获取商家统计数据
    
    参数：
    - merchant_id: 商家 ID
    
    返回：
    - 商家统计数据
    """
    try:
        stats = await StatisticsManager.get_merchant_stats(merchant_id)
        if not stats:
            raise HTTPException(status_code=404, detail="商家不存在")
        
        return {
            "code": "0000",
            "message": "success",
            "data": stats
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取商家统计失败: {e}")
        raise HTTPException(status_code=500, detail="获取商家统计失败")


# ═══════════════════════════════════════════════════════════════
# 健康检查 API
# ═══════════════════════════════════════════════════════════════

@router.get("/health", summary="健康检查")
async def health_check():
    """
    系统健康检查
    
    返回：
    - status: 系统状态
    - timestamp: 时间戳
    """
    try:
        merchants = await MerchantDataManager.get_all_merchants()
        return {
            "code": "0000",
            "message": "success",
            "data": {
                "status": "healthy",
                "merchants_count": len(merchants),
                "timestamp": __import__("datetime").datetime.now().isoformat()
            }
        }
    except Exception as e:
        logger.error(f"健康检查失败: {e}")
        return {
            "code": "5001",
            "message": "unhealthy",
            "data": {"status": "unhealthy"}
        }
