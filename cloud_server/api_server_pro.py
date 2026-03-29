"""Project Claw 完整 API 服务器 - cloud_server/api_server_pro.py"""
import logging
import json
from fastapi import FastAPI, WebSocket, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
from typing import Optional
import uuid

# 导入必要的模块
from auth_guard import verify_rate_limit_only, verify_session, create_session, invalidate_session
from model_gateway import initialize_model_gateway, get_model_gateway
from cost_tracker import CostTracker, CostRecord, usd_to_cny
import time

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 创建 FastAPI 应用
app = FastAPI(title="Project Claw API Server", version="1.0.0")

# 添加 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局服务实例
cost_tracker = CostTracker()
model_gateway = None

@app.on_event("startup")
async def startup_event():
    """应用启动事件"""
    global model_gateway
    logger.info("🚀 Project Claw API 服务器启动中...")
    
    # 初始化模型网关
    model_gateway = await initialize_model_gateway()
    
    logger.info("✓ 所有服务已初始化")

@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭事件"""
    logger.info("🛑 Project Claw API 服务器关闭中...")
    if model_gateway:
        await model_gateway.close()

# ==================== 认证接口 ====================

@app.post("/auth/login")
async def login(request: Request):
    """微信登录"""
    try:
        data = await request.json()
        code = data.get("code")
        
        if not code:
            raise HTTPException(status_code=400, detail="缺少 code 参数")
        
        # 这里应该调用微信 API 验证 code
        # 为了演示，我们直接生成 session
        user_id = f"user_{uuid.uuid4().hex[:8]}"
        user_info = {
            "user_id": user_id,
            "nickname": "用户",
            "avatar": "",
            "created_at": time.time()
        }
        
        session_id = create_session(user_id, user_info)
        
        logger.info(f"✓ 用户登录: {user_id}")
        
        return {
            "code": 200,
            "message": "登录成功",
            "data": {
                "session_id": session_id,
                "user_info": user_info
            }
        }
    except Exception as e:
        logger.error(f"登录失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/auth/user-info")
async def get_user_info(authorization: str = Header(...)):
    """获取用户信息"""
    try:
        session_id = authorization.replace("Bearer ", "")
        session = verify_session(session_id)
        
        if not session:
            raise HTTPException(status_code=401, detail="会话无效")
        
        return {
            "code": 200,
            "message": "获取成功",
            "data": session["user_info"]
        }
    except Exception as e:
        logger.error(f"获取用户信息失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/auth/logout")
async def logout(authorization: str = Header(...)):
    """登出"""
    try:
        session_id = authorization.replace("Bearer ", "")
        invalidate_session(session_id)
        
        return {
            "code": 200,
            "message": "登出成功"
        }
    except Exception as e:
        logger.error(f"登出失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== 订单接口 ====================

@app.get("/orders/list")
async def list_orders(authorization: str = Header(...)):
    """获取订单列表"""
    try:
        session_id = authorization.replace("Bearer ", "")
        session = verify_session(session_id)
        
        if not session:
            raise HTTPException(status_code=401, detail="会话无效")
        
        # 这里应该从数据库查询订单
        # 为了演示，我们返回示例数据
        orders = [
            {
                "order_id": f"order_{i}",
                "status": "pending" if i % 2 == 0 else "completed",
                "created_at": time.time() - i * 3600,
                "amount": 100 + i * 10
            }
            for i in range(5)
        ]
        
        return {
            "code": 200,
            "message": "获取成功",
            "data": {"orders": orders}
        }
    except Exception as e:
        logger.error(f"获取订单列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/orders/{order_id}")
async def get_order(order_id: str, authorization: str = Header(...)):
    """获取订单详情"""
    try:
        session_id = authorization.replace("Bearer ", "")
        session = verify_session(session_id)
        
        if not session:
            raise HTTPException(status_code=401, detail="会话无效")
        
        # 这里应该从数据库查询订单
        order = {
            "order_id": order_id,
            "status": "pending",
            "created_at": time.time(),
            "amount": 100,
            "items": [
                {"name": "商品1", "price": 50, "quantity": 1},
                {"name": "商品2", "price": 50, "quantity": 1}
            ]
        }
        
        return {
            "code": 200,
            "message": "获取成功",
            "data": order
        }
    except Exception as e:
        logger.error(f"获取订单详情失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== 成本接口 ====================

@app.get("/cost/analysis")
async def analyze_cost(
    start_date: str,
    end_date: str,
    tenant_id: Optional[str] = None,
    authorization: str = Header(...)
):
    """成本分析"""
    try:
        session_id = authorization.replace("Bearer ", "")
        session = verify_session(session_id)
        
        if not session:
            raise HTTPException(status_code=401, detail="会话无效")
        
        # 获取成本数据
        if tenant_id:
            cost_data = cost_tracker.get_tenant_cost(tenant_id)
        else:
            cost_data = cost_tracker.get_daily_cost(start_date)
        
        return {
            "code": 200,
            "message": "获取成功",
            "data": cost_data
        }
    except Exception as e:
        logger.error(f"成本分析失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/cost/daily-stats")
async def get_daily_stats(days: int = 30, authorization: str = Header(...)):
    """获取每日成本统计"""
    try:
        session_id = authorization.replace("Bearer ", "")
        session = verify_session(session_id)
        
        if not session:
            raise HTTPException(status_code=401, detail="会话无效")
        
        # 这里应该从数据库查询每日成本
        # 为了演示，我们返回示例数据
        data = [
            {
                "date": f"2024-01-{i:02d}",
                "cost_usd": 10 + i * 0.5,
                "cost_cny": (10 + i * 0.5) * 7
            }
            for i in range(1, days + 1)
        ]
        
        return {
            "code": 200,
            "message": "获取成功",
            "data": data
        }
    except Exception as e:
        logger.error(f"获取每日成本统计失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== 舰队接口 ====================

@app.get("/fleet/status")
async def get_fleet_status(authorization: str = Header(...)):
    """获取舰队状态"""
    try:
        session_id = authorization.replace("Bearer ", "")
        session = verify_session(session_id)
        
        if not session:
            raise HTTPException(status_code=401, detail="会话无效")
        
        # 这里应该从舰队管理器获取状态
        # 为了演示，我们返回示例数据
        stats = {
            "total_boxes": 10,
            "idle_boxes": 6,
            "busy_boxes": 3,
            "error_boxes": 1,
            "total_orders": 100,
            "avg_confidence": 0.85,
            "pending_tasks": 5,
            "boxes": [
                {
                    "box_id": f"box_{i}",
                    "status": ["idle", "busy", "error"][i % 3],
                    "daily_orders": 10 + i,
                    "confidence": 0.8 + i * 0.01
                }
                for i in range(10)
            ]
        }
        
        return {
            "code": 200,
            "message": "获取成功",
            "data": stats
        }
    except Exception as e:
        logger.error(f"获取舰队状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/fleet/pending-tasks")
async def get_pending_tasks(limit: int = 100, authorization: str = Header(...)):
    """获取待审批任务"""
    try:
        session_id = authorization.replace("Bearer ", "")
        session = verify_session(session_id)
        
        if not session:
            raise HTTPException(status_code=401, detail="会话无效")
        
        # 这里应该从数据库查询待审批任务
        # 为了演示，我们返回示例数据
        tasks = [
            {
                "task_id": f"task_{i}",
                "box_id": f"box_{i % 10}",
                "confidence": 0.5 + i * 0.01,
                "reason": "置信度过低",
                "created_at": time.time() - i * 3600,
                "state_data": {}
            }
            for i in range(min(limit, 10))
        ]
        
        return {
            "code": 200,
            "message": "获取成功",
            "data": tasks
        }
    except Exception as e:
        logger.error(f"获取待审批任务失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/fleet/approve-task")
async def approve_task(request: Request, authorization: str = Header(...)):
    """批准任务"""
    try:
        session_id = authorization.replace("Bearer ", "")
        session = verify_session(session_id)
        
        if not session:
            raise HTTPException(status_code=401, detail="会话无效")
        
        data = await request.json()
        task_id = data.get("task_id")
        decision = data.get("decision")
        
        logger.info(f"✓ 任务已批准: {task_id} ({decision})")
        
        return {
            "code": 200,
            "message": "批准成功"
        }
    except Exception as e:
        logger.error(f"批准任务失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== WebSocket 接口 ====================

@app.websocket("/ws/audio/{session_id}")
async def websocket_audio(websocket: WebSocket, session_id: str):
    """音频 WebSocket"""
    await websocket.accept()
    logger.info(f"✓ WebSocket 连接已建立: {session_id}")
    
    try:
        while True:
            data = await websocket.receive_bytes()
            
            # 这里应该处理音频数据
            # 为了演示，我们直接回显
            await websocket.send_bytes(data)
    
    except Exception as e:
        logger.error(f"WebSocket 错误: {e}")
    finally:
        logger.info(f"✓ WebSocket 连接已关闭: {session_id}")

# ==================== 健康检查 ====================

@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "code": 200,
        "message": "服务正常",
        "timestamp": time.time()
    }

# ==================== 主函数 ====================

if __name__ == "__main__":
    uvicorn.run(
        "api_server_pro:app",
        host="0.0.0.0",
        port=8765,
        reload=True,
        log_level="info"
    )
