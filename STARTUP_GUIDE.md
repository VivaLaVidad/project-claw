# Project Claw 完整启动指南

## 🚀 一键启动

### 方式一：启动所有服务（包括微信开发者工具）

```powershell
cd "d:\桌面\Project Claw"
.\start_all.ps1
```

### 方式二：仅启动后端服务（不启动微信开发者工具）

```powershell
cd "d:\桌面\Project Claw"
.\start_all.ps1 -NoWechat
```

### 方式三：手动启动（分别在三个终端）

**终端 1：启动云端服务**
```powershell
cd "d:\桌面\Project Claw"
python run_stack.py signaling siri
```

**终端 2：启动 B端 Agent**
```powershell
cd "d:\桌面\Project Claw"
.\start_edge.ps1
```

**终端 3：打开微信开发者工具**
- 下载：https://developers.weixin.qq.com/miniprogram/dev/devtools/download.html
- 导入项目：`d:\桌面\Project Claw\miniprogram`
- **重要：详情 → 本地设置 → 勾选「不校验合法域名」**

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                    微信小程序 (C端/B端UI)                    │
│  • pages/index      → C端发现页（砍价、广播、对话）          │
│  • pages/dialogue   → 实时对话页（WS流式）                  │
│  • pages/orders     → 订单历史页                            │
│  • pages/merchant   → B端控制台（策略配置、Agent状态）       │
└────────────────────────┬──────────────────────────────────────┘
                         │ HTTP/WebSocket
                         ↓
┌─────────────────────────────────────────────────────────────┐
│         signaling:8765 (A2A 信令服务器)                      │
│  • POST /intent              → 快速广播                      │
│  • POST /a2a/intent          → 全自动谈判                    │
│  • POST /a2a/dialogue/start  → 启动对话                      │
│  • WS /ws/a2a/client/:id     → C端实时消息                   │
│  • WS /ws/a2a/merchant/:id   → B端实时消息                   │
└────────────────────────┬──────────────────────────────────────┘
                         │
        ┌────────────────┼────────────────┐
        ↓                ↓                ↓
   ┌─────────┐    ┌──────────┐    ┌──────────────┐
   │ siri    │    │ edge_box │    │ Redis/内存   │
   │:8010    │    │ (B端)    │    │ (缓存/状态)  │
   │         │    │          │    │              │
   │ LLM API │    │ Agent    │    │ • 画像       │
   │ DeepSeek│    │ 谈判引擎 │    │ • 订单       │
   │         │    │ 物理执行 │    │ • 会话       │
   └─────────┘    └──────────┘    └──────────────┘
        ↑              ↑
        └──────────────┘
         LLM 谈判调用
```

---

## 🔄 完整业务流程

### 场景 1：C端快速广播

```
1. 小程序输入商品 + 预算
   ↓
2. POST /intent → signaling:8765
   ├─ 生成 intent_id
   ├─ 广播给所有在线 B端 Agent
   └─ 返回 offers 列表
   ↓
3. B端 Agent 收到广播
   ├─ 调用 LLM (siri:8010) 生成报价
   ├─ 返回 offer 给 signaling
   └─ signaling 汇总所有报价
   ↓
4. 小程序展示报价
   ├─ 按性价比排序
   ├─ 显示最优报价
   └─ 用户可立即下单
```

### 场景 2：C端全自动谈判

```
1. 小程序点击「Agent 全自动砍价」
   ↓
2. POST /a2a/intent → signaling:8765
   ├─ 创建 A2A 意图
   ├─ 广播给 B端 Agent
   └─ 返回 intent_id
   ↓
3. B端 Agent 多轮谈判
   ├─ 第1轮：初始报价
   ├─ 第2-N轮：根据 LLM 策略砍价
   ├─ 每轮调用 siri:8010 (DeepSeek)
   └─ 最终达成成交价
   ↓
4. 小程序轮询 GET /a2a/intent/:id/result
   ├─ 每 1.5s 查询一次
   ├─ 收到 best_offer 时成交
   └─ 显示最终价格 + 商家信息
```

### 场景 3：C端手动对话

```
1. 小程序点击「手动谈判」
   ↓
2. POST /a2a/dialogue/start → signaling:8765
   ├─ 创建对话会话
   ├─ 返回 session_id
   └─ 跳转对话页
   ↓
3. 建立 WebSocket 连接
   ├─ WS /ws/a2a/client/:clientId
   ├─ 实时接收 B端 Agent 消息
   └─ 实时发送 C端 客户消息
   ↓
4. 多轮对话流程
   ├─ C端发送：「能便宜点吗？」
   ├─ B端 Agent 调用 LLM 生成回复
   ├─ B端发送：「最多打 8 折」
   ├─ 重复直到成交或结束
   └─ 满意度上报驱动 Agent 学习
```

---

## 📊 服务端口映射

| 服务 | 端口 | 协议 | 用途 |
|------|------|------|------|
| signaling | 8765 | HTTP/WS | A2A 信令中枢 |
| siri | 8010 | HTTP | LLM API (DeepSeek) |
| Redis | 6379 | TCP | 缓存/状态存储（可选） |

---

## 🔐 数据流向

```
小程序 (C端)
  ├─ 上传画像 → signaling → Redis (缓存)
  ├─ 发起意图 → signaling → B端 Agent
  ├─ WS 实时消息 → signaling ↔ B端 Agent
  └─ 上报满意度 → signaling → Redis (学习数据)

B端 Agent (edge_box)
  ├─ 接收意图 ← signaling
  ├─ 调用 LLM → siri:8010 (DeepSeek)
  ├─ 生成报价/回复 → signaling
  ├─ 执行物理操作 (MockDriver/uiautomator2)
  └─ 记录交易 → Redis (TransactionLedger)

signaling (中枢)
  ├─ 管理连接 (B端 Agent + C端小程序)
  ├─ 广播意图
  ├─ 汇总报价
  ├─ 路由消息
  └─ 存储状态 → Redis
```

---

## 🛠️ 环境变量配置

关键配置在 `.env`：

```bash
# 信令服务器
SIGNALING_HOST=127.0.0.1
SIGNALING_PORT=8765

# LLM
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_MODEL=deepseek-chat

# B端 Agent
A2A_MERCHANT_ID=box-001
A2A_SIGNING_SECRET=claw-a2a-signing-secret-dev

# 缓存（可选）
REDIS_URL=  # 留空自动降级到内存存储
```

---

## 📱 小程序配置

在 `miniprogram/app.js` 切换环境：

```javascript
const ENV = 'dev';   // 本地调试 127.0.0.1:8765
// const ENV = 'prod';  // Railway 生产环境
```

---

## ✅ 启动检查清单

- [ ] Python 3.11+ 已安装
- [ ] `.env` 文件存在且配置正确
- [ ] 端口 8765、8010 未被占用
- [ ] 微信开发者工具已安装
- [ ] 小程序「不校验合法域名」已勾选
- [ ] Redis 可选（无 Redis 自动降级内存存储）

---

## 🐛 常见问题

### Q: 启动后小程序显示「离线」？
A: 检查 signaling 是否启动成功，查看 signaling 终端是否有错误日志。

### Q: B端 Agent 无法连接？
A: 确保 signaling 已启动，检查 `A2A_MERCHANT_ID` 配置。

### Q: 报价为空？
A: 检查 B端 Agent 是否启动，查看 siri:8010 是否正常。

### Q: 微信开发者工具无法连接服务器？
A: 勾选「不校验合法域名」，确保 127.0.0.1:8765 可访问。

---

## 📚 相关文档

- 小程序 API 层：`miniprogram/api/request.js`
- 后端协议：`shared/claw_protocol.py`
- 信令服务器：`a2a_signaling_server.py`
- B端 Agent：`edge_box/ws_listener.py`
- 配置文件：`.env` 和 `config.py`
