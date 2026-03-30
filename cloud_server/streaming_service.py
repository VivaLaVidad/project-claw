"""
Project Claw v14.3 - SSE Streaming Quotes + WebSocket Command Dispatch
流式报价体验 + 毫秒级指令下发
"""

import asyncio
import json
import time
from typing import AsyncGenerator, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel


class StreamingQuoteService:
    """
    SSE 流式报价服务
    
    用户体验：
    "全城 50 家店的 AI 正在为我疯狂竞价"
    
    技术实现：
    1. 用户发起询价 → 后端广播到所有在线商家
    2. 商家 Agent 并行处理（5090 集群）
    3. 每个报价实时推送给用户（SSE）
    4. 用户看到打字机般的报价流入
    """
    
    def __init__(self):
        self.active_quotes: dict[str, list] = {}  # request_id -> [quotes]
        self.merchant_agents: dict[str, WebSocket] = {}  # merchant_id -> ws
    
    async def stream_quotes(self, request_id: str, timeout_sec: float = 20) -> AsyncGenerator[str, None]:
        """
        SSE 流式推送报价
        
        前端接收示例：
        ```javascript
        const eventSource = new EventSource('/api/v1/trade/request/stream?request_id=xxx');
        eventSource.addEventListener('offer', (e) => {
            const offer = JSON.parse(e.data);
            console.log(`${offer.merchant_id} 报价 ${offer.final_price} 元`);
        });
        ```
        """
        
        self.active_quotes[request_id] = []
        start_time = time.time()
        last_sent_count = 0
        
        try:
            # 首包：开始事件
            yield f"event: start\ndata: {json.dumps({'request_id': request_id, 'timestamp': int(time.time())})}\n\n"
            
            # 持续推送报价
            while time.time() - start_time < timeout_sec:
                current_quotes = self.active_quotes.get(request_id, [])
                
                # 只推送新报价
                if len(current_quotes) > last_sent_count:
                    for quote in current_quotes[last_sent_count:]:
                        # 打字机效果：每个报价单独推送
                        yield f"event: offer\ndata: {json.dumps(quote, ensure_ascii=False)}\n\n"
                        last_sent_count += 1
                
                await asyncio.sleep(0.1)  # 100ms 检查一次
            
            # 结束事件
            yield f"event: end\ndata: {json.dumps({'request_id': request_id, 'total_offers': len(current_quotes)})}\n\n"
        
        finally:
            # 清理
            self.active_quotes.pop(request_id, None)
    
    async def add_quote(self, request_id: str, quote: dict):
        """添加报价（由商家 Agent 调用）"""
        if request_id not in self.active_quotes:
            self.active_quotes[request_id] = []
        
        # 添加时间戳
        quote['received_at'] = time.time()
        self.active_quotes[request_id].append(quote)


class WebSocketCommandDispatcher:
    """
    WebSocket 毫秒级指令下发
    
    用途：
    1. 商家 Agent 连接 → 保持长连接
    2. 平台有新询价 → 毫秒级推送给商家
    3. 商家 Agent 处理 → 返回报价
    4. 平台推送给用户（SSE）
    
    延迟目标：< 10ms
    """
    
    def __init__(self):
        self.merchant_connections: dict[str, WebSocket] = {}  # merchant_id -> ws
        self.pending_commands: dict[str, list] = {}  # merchant_id -> [commands]
    
    async def register_merchant(self, merchant_id: str, websocket: WebSocket):
        """商家 Agent 连接"""
        await websocket.accept()
        self.merchant_connections[merchant_id] = websocket
        
        # 发送欢迎消息
        await websocket.send_json({
            "type": "connected",
            "merchant_id": merchant_id,
            "timestamp": int(time.time() * 1000)  # 毫秒级时间戳
        })
    
    async def dispatch_command(
        self,
        merchant_id: str,
        command_type: str,
        payload: dict,
        timeout_ms: int = 5000
    ) -> Optional[dict]:
        """
        下发指令给商家 Agent
        
        指令类型：
        - "INTENT_BROADCAST": 新询价广播
        - "EXECUTE_TRADE": 成交指令
        - "CANCEL_TRADE": 取消指令
        """
        
        ws = self.merchant_connections.get(merchant_id)
        if not ws:
            return None
        
        command = {
            "type": command_type,
            "payload": payload,
            "timestamp": int(time.time() * 1000),
            "command_id": f"{merchant_id}_{int(time.time() * 1000)}"
        }
        
        try:
            # 发送指令
            await ws.send_json(command)
            
            # 等待响应（超时 5 秒）
            response = await asyncio.wait_for(
                ws.receive_json(),
                timeout=timeout_ms / 1000
            )
            
            return response
        
        except asyncio.TimeoutError:
            return {"status": "timeout", "command_id": command["command_id"]}
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    async def broadcast_intent(
        self,
        request_id: str,
        intent_payload: dict,
        merchant_ids: list[str]
    ) -> dict:
        """
        广播询价给多个商家
        
        并行下发，收集所有响应
        """
        
        tasks = [
            self.dispatch_command(
                merchant_id,
                "INTENT_BROADCAST",
                {
                    "request_id": request_id,
                    **intent_payload
                }
            )
            for merchant_id in merchant_ids
        ]
        
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        return {
            "request_id": request_id,
            "total_merchants": len(merchant_ids),
            "responses": responses,
            "timestamp": int(time.time() * 1000)
        }
    
    async def handle_merchant_connection(self, merchant_id: str, websocket: WebSocket):
        """处理商家 WebSocket 连接"""
        await self.register_merchant(merchant_id, websocket)
        
        try:
            while True:
                # 接收商家的消息（报价、心跳等）
                data = await websocket.receive_json()
                
                if data.get("type") == "heartbeat":
                    # 心跳响应
                    await websocket.send_json({
                        "type": "heartbeat_ack",
                        "timestamp": int(time.time() * 1000)
                    })
                
                elif data.get("type") == "quote":
                    # 商家报价 → 推送给用户（由上层处理）
                    pass
        
        except WebSocketDisconnect:
            self.merchant_connections.pop(merchant_id, None)
        except Exception as e:
            print(f"WebSocket error for {merchant_id}: {e}")
            self.merchant_connections.pop(merchant_id, None)


class A2ANegotiationService:
    """
    A2A 谈判引擎
    
    流程：
    1. 用户发起询价 → 平台广播给 50 家商家
    2. 每家商家的 Agent 独立处理（5090 集群）
    3. Agent 可以多轮谈判（最多 5 轮）
    4. 每轮谈判结果实时推送给用户
    5. 用户选择最优报价 → 成交
    """
    
    def __init__(self, streaming_service: StreamingQuoteService, ws_dispatcher: WebSocketCommandDispatcher):
        self.streaming = streaming_service
        self.ws_dispatcher = ws_dispatcher
    
    async def initiate_negotiation(
        self,
        request_id: str,
        client_id: str,
        item_name: str,
        demand_text: str,
        max_price: float,
        merchant_ids: list[str]
    ) -> dict:
        """
        发起 A2A 谈判
        
        时间线：
        T+0ms: 平台接收询价
        T+1ms: 广播给 50 家商家
        T+10ms: 第一家商家返回初始报价
        T+50ms: 大部分商家返回报价
        T+100ms: 用户看到完整报价列表
        """
        
        start_time = time.time()
        
        # 1. 广播询价给所有商家
        broadcast_result = await self.ws_dispatcher.broadcast_intent(
            request_id,
            {
                "client_id": client_id,
                "item_name": item_name,
                "demand_text": demand_text,
                "max_price": max_price
            },
            merchant_ids
        )
        
        # 2. 收集报价
        for response in broadcast_result.get("responses", []):
            if response and response.get("type") == "quote":
                await self.streaming.add_quote(request_id, response.get("payload", {}))
        
        elapsed_ms = (time.time() - start_time) * 1000
        
        return {
            "request_id": request_id,
            "status": "negotiating",
            "elapsed_ms": elapsed_ms,
            "merchants_contacted": len(merchant_ids),
            "quotes_received": len(self.streaming.active_quotes.get(request_id, []))
        }


# ═══════════════════════════════════════════════════════════════════════════
# 📊 Pydantic 数据模型
# ═══════════════════════════════════════════════════════════════════════════

class StreamingQuoteRequest(BaseModel):
    """流式报价请求"""
    request_id: str
    client_id: str
    item_name: str
    demand_text: str
    max_price: float
    timeout_sec: float = 20


class WebSocketCommand(BaseModel):
    """WebSocket 指令"""
    type: str  # INTENT_BROADCAST / EXECUTE_TRADE / CANCEL_TRADE
    payload: dict
    timestamp: int


class QuoteResponse(BaseModel):
    """报价响应"""
    offer_id: str
    merchant_id: str
    merchant_name: str
    final_price: float
    reply_text: str
    match_score: float
    eta_minutes: int
    received_at: float
