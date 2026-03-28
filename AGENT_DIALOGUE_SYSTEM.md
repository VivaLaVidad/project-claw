# Project Claw - B端Agent ↔ C端Agent 完整对话系统

## 📋 系统架构概览

```
微信小程序 (C端 Agent)
    ↕ HTTP/WebSocket
signaling:8765 (信令中枢)
    ↕
B端 Agent (edge_box)
    ↕
siri:8010 (LLM)
```

---

## 🔄 完整对话流程

### 第一步：C端发起意图

```python
# 小程序用户输入
POST /a2a/intent
{
    "client_id": "c_1711756800000_abc123",
    "item_name": "牛肉面",
    "expected_price": 15,
    "max_distance_km": 8.0,
    "timestamp": 1711756800.123,
    "client_profile": {
        "budget_min": 10,
        "budget_max": 30,
        "price_sensitivity": 0.8,
        "time_urgency": 0.5,
    }
}

# signaling 处理
- 生成 intent_id (UUID)
- 存储到 Redis
- 广播给所有在线 B端 Agent
- 返回 intent_id
```

### 第二步：B端 Agent 接收意图

```python
# B端 Agent 连接
WS /ws/a2a/merchant/box-001

# signaling 广播意图
{
    "type": "a2a_trade_intent",
    "intent_id": "550e8400-e29b-41d4-a716-446655440000",
    "client_id": "c_1711756800000_abc123",
    "item_name": "牛肉面",
    "expected_price": 15,
}

# B端 Agent 处理
async def _handle_intent(self, ws, msg):
    intent = A2A_TradeIntent.model_validate(msg.get("intent", {}))
    
    # 调用 LLM 生成报价
    offer = await self.negotiator.negotiate_intent(
        intent=intent,
        merchant_id="box-001",
    )
    
    # 返回报价
    await ws.send(json.dumps({
        "type": "a2a_merchant_offer",
        "offer": {
            "offer_id": str(uuid4()),
            "intent_id": intent.intent_id,
            "merchant_id": "box-001",
            "offered_price": 12.5,
            "is_accepted": True,
            "reason": "新鲜现做，保证品质"
        },
    }, ensure_ascii=False))
```

### 第三步：signaling 汇总报价

```python
# signaling 收集所有报价
{
    "intent_id": "550e8400-e29b-41d4-a716-446655440000",
    "offers": [
        {
            "offer_id": "uuid-1",
            "merchant_id": "box-001",
            "offered_price": 12.5,
            "match_score": 92.5,
            "eta_minutes": 20,
        },
    ],
    "total_merchants": 1,
    "responded": 1,
    "elapsed_ms": 1234.5,
}

# 返回给小程序
GET /a2a/intent/{intent_id}/result
```

### 第四步：C端选择报价启动对话

```python
# 小程序点击「立即下单」
POST /a2a/dialogue/start
{
    "intent": {
        "intent_id": "550e8400-e29b-41d4-a716-446655440000",
        "client_id": "c_1711756800000_abc123",
        "item_name": "牛肉面",
        "expected_price": 15,
    },
    "merchant_id": "box-001",
    "opening_text": "预算15元，能给我最优惠的牛肉面吗？"
}

# signaling 创建会话
{
    "session_id": "sess-550e8400-e29b-41d4-a716-446655440000",
    "intent_id": "550e8400-e29b-41d4-a716-446655440000",
    "client_id": "c_1711756800000_abc123",
    "merchant_id": "box-001",
    "status": "OPEN",
}
```

### 第五步：实时 WebSocket 对话

```python
# 小程序建立 WS
WS /ws/a2a/client/c_1711756800000_abc123

# B端 Agent 建立 WS
WS /ws/a2a/dialogue/merchant/box-001

# 小程序发送消息
{
    "type": "a2a_dialogue_turn",
    "turn": {
        "turn_id": "turn-1",
        "session_id": "sess-550e8400-e29b-41d4-a716-446655440000",
        "round": 1,
        "sender_role": "CLIENT",
        "sender_id": "c_1711756800000_abc123",
        "receiver_role": "MERCHANT",
        "receiver_id": "box-001",
        "text": "预算15元，能给我最优惠的牛肉面吗？",
        "expected_price": 15,
        "timestamp": 1711756800.456,
    }
}

# signaling 路由给 B端 Agent
# B端 Agent 调用 LLM 生成回复
async def negotiate_dialogue_turn(
    self,
    session_id: str,
    client_text: str,
    expected_price: float,
    round_no: int,
) -> dict:
    # 构建 LLM 提示词
    prompt = f"""
    你是一个热情的店老板。
    客户说：{client_text}
    客户预算：{expected_price}元
    
    请生成简短、接地气的回复，并给出报价。
    """
    
    # 调用 DeepSeek
    response = await self.llm_client.chat(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=200,
    )
    
    generated_text = response.choices[0].message.content
    offered_price = self._extract_price(generated_text)
    
    return {
        "turn_id": str(uuid4()),
        "session_id": session_id,
        "round": round_no + 1,
        "sender_role": "MERCHANT",
        "sender_id": "box-001",
        "receiver_role": "CLIENT",
        "receiver_id": client_id,
        "text": generated_text,
        "offered_price": offered_price,
        "is_final": offered_price <= expected_price * 0.9,
        "timestamp": time.time(),
    }

# B端 Agent 返回回复
{
    "type": "a2a_dialogue_turn",
    "turn": {
        "turn_id": "turn-2",
        "session_id": "sess-550e8400-e29b-41d4-a716-446655440000",
        "round": 2,
        "sender_role": "MERCHANT",
        "sender_id": "box-001",
        "receiver_role": "CLIENT",
        "receiver_id": "c_1711756800000_abc123",
        "text": "兄弟，新鲜现做，12块钱给你来一碗，保证好吃！",
        "offered_price": 12.0,
        "is_final": True,
        "timestamp": 1711756800.789,
    }
}

# signaling 路由给小程序
# 小程序展示对话
```

### 第六步：成交与支付

```python
# 小程序检测 is_final=True，显示成交弹窗
# 用户点击「接受并下单」

POST /execute_trade
{
    "intent_id": "550e8400-e29b-41d4-a716-446655440000",
    "client_id": "c_1711756800000_abc123",
    "merchant_id": "box-001",
    "final_price": 12.0,
}

# signaling 转发给 B端 Agent
# B端 Agent 执行支付验证
class PaymentVerifier:
    async def handle_execute_trade(
        self,
        intent_id: str,
        client_id: str,
        merchant_id: str,
        final_price: float,
    ) -> str:
        # 步骤 A：生成收款码
        trade_id = f"trade-{uuid4()}"
        qr_code = await self._generate_payment_qr(
            merchant_id=merchant_id,
            amount=final_price,
            trade_id=trade_id,
        )
        
        # 通知 UI 显示收款码
        await notify_and_send_qrcode(final_price, qr_code, self._driver)
        
        # 步骤 B：60s 视觉轮询
        result = await self._poll_payment_visual(
            trade_id=trade_id,
            timeout_sec=60,
        )
        
        if result.status == "SUCCESS":
            # 返回成功 ACK
            await self._send_payment_ack(
                intent_id=intent_id,
                trade_id=trade_id,
                proof_hash=result.visual_proof_hash,
            )
        else:
            # 返回超时
            await self._send_trade_timeout(
                intent_id=intent_id,
                trade_id=trade_id,
                reason="Payment timeout",
            )
        
        return trade_id

# B端 Agent 返回成功 ACK
{
    "type": "PAYMENT_SUCCESS_ACK",
    "intent_id": "550e8400-e29b-41d4-a716-446655440000",
    "trade_id": "trade-uuid",
    "merchant_id": "box-001",
    "visual_proof_hash": "sha256_hash",
    "ocr_snippet": "支付成功 12.00元",
    "elapsed_sec": 8.5,
}

# signaling 记录订单
OrderStore.create_order(
    intent_id=intent_id,
    client_id=client_id,
    merchant_id=merchant_id,
    final_price=12.0,
    status="EXECUTED",
    trade_id=trade_id,
)

# 小程序收到成交确认
# 显示「✅ 成交！¥12.0」
```

### 第七步：满意度上报

```python
# 小程序弹出满意度问卷
POST /a2a/dialogue/satisfaction
{
    "session_id": "sess-550e8400-e29b-41d4-a716-446655440000",
    "client_id": "c_1711756800000_abc123",
    "overall": 85,
    "price": 90,
    "time": 80,
}

# signaling 存储反馈
Redis.hset(
    f"satisfaction:{session_id}",
    mapping={
        "overall": 85,
        "price": 90,
        "time": 80,
        "timestamp": time.time(),
    }
)

# B端 Agent 定期读取反馈，优化策略
```

---

## 🏗️ 核心数据结构

```python
class A2A_TradeIntent(BaseModel):
    intent_id: UUID
    client_id: str
    item_name: str
    expected_price: float
    max_distance_km: float
    timestamp: float
    client_profile: dict

class A2A_DialogueSession(BaseModel):
    session_id: UUID
    intent_id: UUID
    client_id: str
    merchant_id: str
    status: str  # OPEN / CLOSED
    round: int

class A2A_DialogueTurn(BaseModel):
    turn_id: UUID
    session_id: UUID
    round: int
    sender_role: str  # CLIENT / MERCHANT
    sender_id: str
    receiver_role: str
    receiver_id: str
    text: str
    expected_price: Optional[float]
    offered_price: Optional[float]
    is_final: bool
    timestamp: float
```

---

## 🔐 安全机制

- **消息签名**：HMAC-SHA256
- **加密**：AES-GCM
- **幂等性**：Redis 去重
- **防重放**：Nonce 机制

---

## 📊 监控指标

```python
metrics = {
    "intent_total": 0,
    "execute_total": 0,
    "execute_success": 0,
    "avg_negotiation_rounds": 0,
    "avg_satisfaction": 0,
}
```

---

## ✅ 完整启动

```bash
# 终端 1
python run_stack.py signaling siri dashboard

# 终端 2
.\start_edge.ps1

# 微信开发者工具
# 导入 miniprogram，清空缓存，刷新
```

验证：小程序顶部显示 `● 在线 1 商家`
