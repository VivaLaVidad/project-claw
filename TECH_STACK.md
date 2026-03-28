# Project Claw v3.0 - 技术架构与运行指南

## 📋 项目概述

**Project Claw** 是一个工业级 AI 驱动的 B2C 智能砍价系统，采用三端架构：
- **C端**（消费者）：微信小程序 + Web 演示页
- **B端**（商家）：本地 EdgeBox Agent
- **云端**（中枢）：Railway 信令服务器 + Streamlit 监控大屏

核心能力：C端发起砍价意图 → 云端广播给所有在线B端 → B端AI自动报价 → 实时成交

---

## 🏗️ 技术栈

### 后端（Python）
| 组件 | 技术 | 用途 |
|------|------|------|
| Web 框架 | FastAPI 0.111.0 | 信令服务器、HTTP API |
| 异步运行时 | asyncio | 并发处理 WS 连接 |
| WebSocket | websockets 12.0 | B/C 端实时通信 |
| 数据验证 | Pydantic 2.7.1 | 请求/响应模型 |
| LLM 调用 | requests + tenacity | DeepSeek API 调用 + 重试 |
| 安全通信 | cryptography 42.0.8 | AES-GCM 加密 + HMAC 签名 |
| 存储 | Redis 5.0.4 | 幂等性、状态缓存 |
| 监控大屏 | Streamlit 1.35.0 | 实时数据可视化 |

### 前端（小程序 + Web）
| 组件 | 技术 | 用途 |
|------|------|------|
| 小程序框架 | WeChat Mini Program | C端用户界面 |
| 小程序 API | wx.request / wx.connectSocket | HTTP + WebSocket |
| Web 演示 | HTML5 + Vanilla JS | mock_client.html |
| 大屏前端 | Streamlit + Pandas | 上帝视角监控 |

### 部署
| 环境 | 平台 | 配置 |
|------|------|------|
| 云端 Hub | Railway | uvicorn + 8080 端口 |
| 大屏 | Streamlit Cloud | 自动部署 |
| 本地 B端 | Windows/Mac/Linux | Python 3.9+ |

---

## 🔄 三端架构与数据流

```
┌─────────────────────────────────────────────────────────────────┐
│                        Railway 云端 Hub                          │
│  a2a_signaling_server.py (FastAPI)                              │
│  ├─ /health              → 健康检查 + 在线商家数                 │
│  ├─ /stats               → 实时统计（谈判数、成交率等）          │
│  ├─ /intent              → C端发起砍价意图                       │
│  ├─ /execute_trade       → 成交下单                             │
│  ├─ /ws/a2a/merchant/{id} → B端 Agent 连接点                    │
│  ├─ /ws/a2a/client/{id}   → C端 WebSocket                       │
│  └─ /ws/audit_stream      → 审计事件流（驱动大屏）              │
└─────────────────────────────────────────────────────────────────┘
         ↑                    ↑                    ↑
         │                    │                    │
    [C端小程序]          [B端 EdgeBox]      [Streamlit大屏]
    ├─ 发起意图          ├─ 连接 WS          ├─ 拉取 /stats
    ├─ 接收报价          ├─ 自动报价         ├─ 监听 /ws/audit_stream
    └─ 成交下单          └─ 执行交易         └─ 实时展示数据
```

---

## 🚀 各部分运行原理

### 1. Railway 云端 Hub（a2a_signaling_server.py）

**启动方式**：
```bash
uvicorn a2a_signaling_server:app --host 0.0.0.0 --port 8080
```

**核心流程**：
```
1. B端 Agent 连接 /ws/a2a/merchant/box-001
   ↓
2. C端发送 POST /intent（砍价意图）
   ↓
3. Hub 广播意图给所有在线 B端
   ↓
4. B端 Agent 收到意图 → 调用 DarkNetNegotiator → 自动报价
   ↓
5. B端发送报价回 Hub
   ↓
6. Hub 汇总所有报价 → 返回给 C端
   ↓
7. C端选择最优报价 → POST /execute_trade
   ↓
8. Hub 下发成交指令给 B端 → 记录订单
```

**关键类**：
- `ConnectionManager`：管理所有 B端 WS 连接
- `TradeArena`：意图广播 + 报价汇总
- `DialogueArena`：多轮对话管理
- `AuditBroadcaster`：事件广播给大屏

---

### 2. B端 EdgeBox Agent（edge_box/ws_listener.py）

**启动方式**：
```powershell
$env:A2A_SIGNALING_URL = "wss://project-claw-production.up.railway.app/ws/a2a/merchant/box-001"
python -m edge_box.ws_listener
```

**核心流程**：
```
1. 连接 Railway Hub 的 /ws/a2a/merchant/box-001
   ↓
2. 监听意图消息（type: "a2a_trade_intent"）
   ↓
3. 调用 DarkNetNegotiator.negotiate_intent()
   - 查询本地菜单（local_memory.py）获取底价
   - 调用 DeepSeek LLM 生成报价理由
   - 返回 A2A_MerchantOffer
   ↓
4. 发送报价回 Hub
   ↓
5. 监听成交指令（type: "execute_trade"）
   ↓
6. 调用 notify_and_send_qrcode() 生成支付二维码
```

**关键类**：
- `EdgeBoxWSListener`：WS 连接管理
- `DarkNetNegotiator`：AI 谈判引擎
  - `negotiate_intent()`：一次性报价
  - `negotiate_dialogue_turn()`：多轮对话

---

### 3. C端小程序（miniprogram/）

**启动方式**：
- 微信开发者工具打开 `miniprogram/` 目录
- 或双击 `mock_client.html` 进行 Web 演示

**核心页面**：

| 页面 | 功能 |
|------|------|
| `pages/index/index` | 发现商家、发起砍价 |
| `pages/orders/orders` | 订单历史、成交记录 |
| `pages/merchant/merchant` | B端商家控制台（配置谈判策略） |
| `pages/dialogue/dialogue` | 多轮对话页面 |

**关键 API 调用**：
```javascript
// 发起砍价意图
POST /intent
{
  client_id: "c_xxx",
  demand_text: "龙虾",
  max_price: 25.0,
  client_profile: { budget_min: 10, budget_max: 30, ... }
}

// 接收报价（WebSocket）
ws://railway/ws/a2a/client/{client_id}
→ { type: "offers", offers: [...] }

// 成交下单
POST /execute_trade
{
  intent_id: "xxx",
  merchant_id: "box-001",
  final_price: 18.5
}
```

---

### 4. 上帝视角大屏（god_mode_dashboard.py）

**启动方式**：
```bash
streamlit run god_mode_dashboard.py
```

**显示内容**：
- 实时在线商家数
- 总谈判次数 + 成交率
- 最近成交明细（价格、商家、节省金额）
- 实时审计事件流（WebSocket 监听）

**数据来源**：
```
1. 定时拉取 /stats（每 2 秒）
   ↓
2. WebSocket 监听 /ws/audit_stream
   ↓
3. 接收事件：
   - intent_broadcasted
   - offer_received
   - trade_executed
   ↓
4. 实时更新 Streamlit 组件
```

---

## 🔐 安全机制

### A2A 通信加密
```
所有 B/C ↔ Hub 的消息都经过：
1. AES-GCM 加密（settings.A2A_ENCRYPTION_KEY）
2. HMAC-SHA256 签名（settings.A2A_SIGNING_SECRET）
3. Nonce 重放保护（NonceReplayProtector）
```

### 幂等性保证
```
每个 /execute_trade 请求都有 idempotency_key
→ Redis 存储已处理的 key
→ 重复请求返回相同结果（不重复扣款）
```

---

## 📊 数据存储

| 存储 | 用途 | 实现 |
|------|------|------|
| 订单记录 | 意图、报价、成交 | OrderStore (aiosqlite) |
| 幂等性 | 防重复交易 | IdempotencyStore (Redis) |
| 画像缓存 | C/B 端个性化数据 | AgentProfileStore (Redis) |
| 本地菜单 | B端底价查询 | LocalMemory (CSV + SQLite) |

---

## 🎯 一键启动

### 完整启动（推荐）
```powershell
cd "D:\桌面\Project Claw"
.\start.ps1
```

自动启动：
1. B端 Agent（新窗口）
2. 上帝视角大屏（新窗口）
3. C端演示页（浏览器）

### 单独启动

**仅启动 B端**：
```powershell
.\start_edge.ps1
```

**仅启动大屏**：
```powershell
streamlit run god_mode_dashboard.py
```

**仅启动本地 Hub**（不依赖 Railway）：
```powershell
python run_stack.py signaling
```

---

## 🔍 诊断工具

**全项目健康检查**：
```powershell
.\doctor.ps1
```

检查项：
- Python 环境
- 关键依赖
- 项目文件
- .env 配置
- Railway 连通性
- Git 状态

---

## 📦 依赖清单（requirements.txt）

**云端生产依赖**（Railway 部署）：
```
fastapi==0.111.0
uvicorn[standard]==0.29.0
websockets==12.0
pydantic==2.7.1
requests==2.32.2
cryptography==42.0.8
redis==5.0.4
```

**本地开发依赖**（可选）：
```
streamlit==1.35.0
pandas==2.0.0
easyocr==1.7.0  # 仅 Edge Box 需要
torch==2.0.0    # 仅 Edge Box 需要
```

---

## 🚨 常见问题

### Q: 小程序显示「0 在线商家」
**A**: B端 Agent 没有运行。执行 `.\start_edge.ps1` 启动 B端。

### Q: Railway 部署失败
**A**: 检查 `requirements.txt` 是否包含超重依赖（torch、easyocr）。已精简为仅云端必需的 15 个包。

### Q: WebSocket 连接超时
**A**: 检查防火墙是否阻止 WSS 连接。或在本地用 `python run_stack.py signaling` 启动本地 Hub。

### Q: 大屏数据不更新
**A**: 确保 B端 Agent 在线（`/health` 返回 `merchants > 0`），且 WebSocket 连接正常。

---

## 📈 性能指标

| 指标 | 目标 | 实现 |
|------|------|------|
| 意图广播延迟 | < 100ms | asyncio 并发 + 无状态设计 |
| 报价汇总时间 | < 3s | 可配置超时 + 部分报价返回 |
| 大屏刷新频率 | 2s/次 | Streamlit rerun + WebSocket 事件 |
| 并发连接数 | 100+ | FastAPI + uvicorn workers |
| 内存占用 | < 100MB | 精简依赖 + 流式处理 |

---

## 🔗 关键文件导航

```
Project Claw/
├── a2a_signaling_server.py      ← 云端 Hub（核心）
├── config.py                     ← 全局配置
├── requirements.txt              ← 依赖清单
├── Procfile                      ← Railway 启动命令
├── railway.toml                  ← Railway 部署配置
│
├── edge_box/
│   └── ws_listener.py            ← B端 Agent（核心）
│
├── cloud_server/
│   ├── a2a_orchestrator.py       ← 意图广播 + 报价汇总
│   ├── dialogue_arena.py         ← 多轮对话管理
│   └── match_orchestrator.py     ← 匹配引擎
│
├── miniprogram/                  ← 微信小程序
│   ├── app.js                    ← 全局入口
│   ├── api/request.js            ← API 层
│   ├── utils/profile.js          ← 画像管理
│   └── pages/                    ← 四个页面
│
├── god_mode_dashboard.py         ← 上帝视角大屏
├── mock_client.html              ← C端 Web 演示
│
├── start.ps1                     ← 一键启动脚本
├── start_edge.ps1                ← B端启动脚本
├── doctor.ps1                    ← 诊断工具
└── run_stack.py                  ← 本地 Hub 启动
```

---

## 🎓 学习路径

1. **理解架构**：阅读本文档的「三端架构」部分
2. **本地运行**：`.\start.ps1` 启动全栈
3. **查看日志**：各窗口的控制台输出
4. **修改配置**：编辑 `.env` 或 `config.py`
5. **扩展功能**：修改 `agent_workflow.py` 的谈判逻辑

---

**最后更新**：2026-03-28  
**版本**：v3.0 工业级商业版  
**维护者**：VivaLaVidad
