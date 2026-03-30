# Project Claw v14.3 - 项目总体描述

## 一句话定义
**实时多商家询价撮合平台**：消费者通过微信小程序发起询价 → 云端信令塔广播给多家商户 → 商户 AI 秒速报价 → 消费者选择成交。

---

## 核心业务流程

```
消费者(C端)                    云端信令塔                    商户(B端)
   |                              |                           |
   |-- 发起询价 (SSE流式) -------->|                           |
   |                              |-- 广播询价 (WebSocket) --->|
   |                              |                    [本地RAG+LLM]
   |                              |<-- 报价回传 ---------|
   |<-- 流式推送报价 (SSE) --------|                           |
   |                              |                           |
   |-- 选择报价 + 确认成交 ------->|                           |
   |                              |-- 执行成交指令 ---------->|
   |                              |<-- 设备回执 ---------|
   |<-- 成交确认 --------|
```

---

## 技术栈全景

### 前端（C端小程序）
- **框架**：微信小程序原生 (WXML + WXSS + JavaScript)
- **核心特性**：
  - SSE 流式询价（3-5s 快速返回）
  - WebSocket 心跳保活 + 自动重连
  - 毫秒级精确倒计时（100ms 更新）
  - 本地存储 + 历史订单管理

### 后端（云端信令塔）
- **框架**：FastAPI (Python 异步)
- **核心模块**：
  - **JWT 鉴权**：自实现 HS256 签名（无依赖）
  - **WebSocket 连接池**：管理商户/消费者长连接
  - **TradeCoordinator**：询价状态机 + 报价聚合
  - **地理过滤**：Haversine 距离算法，按半径筛选商户
  - **SQLite 订单库**：持久化交易记录
  - **速率限制**：每分钟 30 次请求
  - **审计日志**：完整事件追踪

### 商户端（B端边缘盒子）
- **框架**：Python 异步 + LangGraph 状态机
- **核心模块**：
  - **LocalMenuRAG**：本地菜单向量化 + 关键词匹配
  - **AgentWorkflow**：LangGraph 多节点工作流
    - IntentNode：意图识别（订单/闲聊/投诉）
    - RAGNode：菜品检索
    - OfferNode：AI 报价生成
    - ReplyNode：自然语言回复
  - **DeepSeek LLM**：在线调用，生成差异化话术
  - **PhysicalTool**：Android 设备控制（OCR + 点击）
  - **WSListener**：WebSocket 长连接监听

### 共享协议层
- **Pydantic 数据模型**：
  - `TradeRequest`：询价请求
  - `MerchantOffer`：商户报价
  - `OfferBundle`：报价汇总
  - `ExecuteTrade`：成交指令
  - `SignalEnvelope`：通用消息信封
- **消息类型枚举**：TRADE_REQUEST / INTENT_BROADCAST / MERCHANT_OFFER / EXECUTE_TRADE / HEARTBEAT

### 虚拟商家模拟器
- **mock_merchants/multi_merchant_simulator.py**：
  - 同时模拟 7 家虚拟商家在线
  - 每家独立菜单 + 差异化 AI 话术风格
  - 无需真实 Android 设备

---

## 技术亮点

### 1. 流式询价（SSE）
```
传统：等待所有商家回复 → 一次性返回（10-20s）
优化：商家报价即时推送 → 3-5s 首个报价到达
```

### 2. 精确倒计时
```
传统：1s 更新一次，显示 "10s"
优化：100ms 更新一次，显示 "10.2s"（毫秒级）
```

### 3. 心跳保活 + 自动重连
```
WebSocket 每 30s 心跳一次
连接断开自动 5s 后重连
防止长连接无故断开
```

### 4. 地理位置过滤
```
消费者位置 + 商户坐标 → Haversine 距离计算
只广播给 500m 范围内的商户（可配置）
```

### 5. 差异化 AI 报价
```
box-001：招牌面馆（老板风格）
box-002：成都麻辣烫（四川老铁风格）
box-003：广式茶餐厅（斯文靓仔风格）
... 每家独立 LLM 提示词
```

### 6. 完整的错误恢复
```
- 商户离线自动清理
- 报价过期自动标记
- 网络断开自动重连
- 设备异常自动降级
```

---

## 数据流向

```
小程序 (HTTPS/WSS)
    ↓
cpolar 隧道 (公网穿透)
    ↓
Hub (FastAPI 8765)
    ├─ REST API：/api/v1/trade/request (SSE 流式)
    ├─ WebSocket：/ws/merchant/{mid} (商户长连接)
    └─ WebSocket：/ws/client/{cid} (消费者长连接)
    ↓
B端盒子 (edge_box)
    ├─ LocalMenuRAG (菜单检索)
    ├─ AgentWorkflow (LLM 报价)
    └─ PhysicalTool (设备控制)
```

---

## 部署架构

```
开发环境（当前）：
  - Hub：本地 127.0.0.1:8765
  - cpolar：免费隧道 60d774b8.r19.cpolar.top
  - B端：本地 edge_box.main
  - 虚拟商家：本地 mock_merchants/multi_merchant_simulator.py

生产环境（推荐）：
  - Hub：Railway / Zeabur（自动扩展）
  - 域名：固定备案域名（HTTPS）
  - B端：Docker 容器化部署
  - 商家：多地域分布式部署
```

---

## 核心配置参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `HUB_REQUEST_HARD_TIMEOUT_SEC` | 60 | 询价硬超时（秒） |
| `HUB_SNAPSHOT_TTL_SEC` | 600 | 报价快照保留时间（秒） |
| `HUB_RATE_LIMIT_PER_MIN` | 30 | 速率限制（次/分钟） |
| `MERCHANT_LAT / MERCHANT_LNG` | 31.2304 / 121.4737 | 商户坐标（上海） |
| `SKIP_SEMANTIC_RAG` | 1 | 跳过向量化，用关键词匹配 |
| `DEEPSEEK_API_KEY` | - | LLM API 密钥 |

---

## 工业级特性

✅ **高可用**：心跳保活 + 自动重连 + 故障转移  
✅ **低延迟**：SSE 流式 + tcpNoDelay + 毫秒级倒计时  
✅ **可扩展**：无状态 Hub + 多商家并行 + 地理分片  
✅ **可观测**：完整审计日志 + 性能指标 + 错误追踪  
✅ **安全**：JWT 鉴权 + 速率限制 + 底价保护  
✅ **易运维**：Docker 化 + 环境变量配置 + 热更新菜单  

---

## 项目规模

- **代码行数**：~3000 行（Python + JavaScript）
- **文件数**：30+ 个
- **商家数**：8 家（1 真实 + 7 虚拟）
- **菜品数**：64 道（每家 8 道）
- **并发能力**：100+ 同时询价

---

## 快速启动

```powershell
# 一键启动所有服务
cd "d:\桌面\Project_Claw_v14"
.\start_all.ps1

# 或手动启动
# 终端1：Hub
python -m uvicorn cloud_server.signaling_hub:app --host 0.0.0.0 --port 8765

# 终端2：B端盒子
python -m edge_box.main

# 终端3：虚拟商家
python mock_merchants/multi_merchant_simulator.py

# 终端4：cpolar 隧道
cpolar http 8765
```

---

## 下一步优化方向

1. **实时排序**：按距离 + 评分 + 响应速度动态排序
2. **智能推荐**：基于历史订单推荐商家
3. **支付集成**：微信支付 / 支付宝
4. **评价系统**：消费者评价 + 商家信誉
5. **数据分析**：询价热力图 + 商家排行榜
6. **多语言**：支持英文 / 日文 / 韩文
7. **视频通话**：实时沟通确认细节
