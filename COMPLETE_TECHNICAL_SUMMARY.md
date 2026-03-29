# Project Claw 完整技术架构和逻辑流程总结

## 🏗️ 系统架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                     Project Claw 完整系统                        │
└─────────────────────────────────────────────────────────────────┘

┌──────────────────┐         ┌──────────────────┐         ┌──────────────────┐
│   C端小程序      │         │  Agent对话系统   │         │  B端商家系统     │
│  (WeChat Mini)   │◄───────►│   (FastAPI)      │◄───────►│  (Streamlit)     │
│                  │         │                  │         │                  │
│ • 发现页面       │         │ • 后端API        │         │ • 融资路演大屏   │
│ • 对话页面       │         │ • Agent引擎      │         │ • 商家管理       │
│ • 订单页面       │         │ • 对话管理       │         │ • 订单管理       │
│ • 商家页面       │         │ • 个性化设置     │         │ • 数据展示       │
└──────────────────┘         └──────────────────┘         └──────────────────┘
         ▲                            ▲                            ▲
         │                            │                            │
         └────────────────────────────┼────────────────────────────┘
                                      │
                    ┌─────────────────┴─────────────────┐
                    │                                   │
            ┌───────▼────────┐              ┌──────────▼──────┐
            │   Redis缓存    │              │   SQLite数据库  │
            │  (端口6379)    │              │  (audit.db)     │
            │                │              │  (dlq.db)       │
            │ • 用户画像     │              │                 │
            │ • 对话历史     │              │ • 交易记录      │
            │ • 订单缓存     │              │ • 用户数据      │
            └────────────────┘              │ • 商家数据      │
                                            └─────────────────┘
```

---

## 🚀 核心技术栈

### 后端技术
```
FastAPI 0.104.1          - Web框架
Uvicorn 0.24.0           - ASGI服务器
Pydantic 2.5.0           - 数据验证
SQLAlchemy 2.0.23        - ORM框架
AsyncPG 0.29.0           - 异步数据库驱动
```

### 前端技术
```
Streamlit 1.28.1         - 融资路演大屏
WeChat Mini Program      - C端小程序
Plotly 5.18.0            - 数据可视化
Pydeck 0.8.1             - 地图展示
```

### 缓存和消息
```
Redis 5.0.1              - 缓存服务
AioRedis 2.0.1           - 异步Redis客户端
```

### LLM和AI
```
OpenAI 1.3.9             - LLM API
DeepSeek API             - 谈判引擎
```

### 工具和库
```
Pandas 2.1.3             - 数据处理
NumPy 1.26.4             - 数值计算
WebSockets 12.0          - 实时通信
Cryptography 41.0.7      - 加密工具
```

---

## 💬 C端Agent 和 B端Agent 对话流程

### 1️⃣ 用户发起购买意图

```
C端小程序
  ↓
用户输入：商品名 + 预期价格
  ↓
调用 POST /a2a/dialogue/start
  ↓
传递参数：
  • client_id: 用户ID
  • item_name: 商品名
  • expected_price: 预期价格
  • client_profile: 用户画像
  • merchant_profile: 商家画像
```

### 2️⃣ C端Agent 生成开场白

```
ClientAgent.generate_opening_message()
  ↓
根据用户画像生成谈判策略：
  • 价格敏感度 (0-1)
  • 时间紧急度 (0-1)
  • 质量偏好 (0-1)
  ↓
调用 DeepSeek LLM
  ↓
生成友好但坚定的开场白
  ↓
返回：开场消息
```

### 3️⃣ B端Agent 生成初始报价

```
MerchantAgent.generate_initial_offer()
  ↓
根据商家画像调整价格：
  • 定价策略 (normal/aggressive/conservative)
  • 谈判风格 (friendly/strict/flexible)
  ↓
计算报价：
  base_price = expected_price * 1.2
  if strategy == "aggressive": offer = base_price * 1.1
  if strategy == "conservative": offer = base_price * 0.95
  ↓
调用 DeepSeek LLM
  ↓
生成吸引人的报价说辞
  ↓
返回：报价消息 + 价格
```

### 4️⃣ 实时对话（WebSocket）

```
C端小程序连接 WebSocket
  ↓
ws://localhost:8765/a2a/dialogue/ws/{session_id}
  ↓
接收对话历史
  ↓
用户查看对话
  ↓
用户发送反价
  ↓
ClientAgent.generate_counter_offer()
  ↓
B端Agent 响应
  ↓
MerchantAgent.respond_to_counter_offer()
  ↓
重复直到达成协议或达到最大轮数
```

### 5️⃣ 对话完成

```
DialogueManager.continue_dialogue()
  ↓
评估最终报价
  ↓
ClientAgent.evaluate_offer()
  ↓
计算满意度：
  if offer_price <= expected_price:
    satisfaction = 0.9 + (discount_rate * 0.1)
  else:
    satisfaction = 1 - (offer_price - expected_price) / expected_price
  ↓
if satisfaction > 0.6:
  accept = True
  ↓
返回最终报价和满意度
  ↓
C端用户确认
  ↓
创建订单
```

---

## 🎯 个性化设置实现

### C端用户个性化设置

```
用户画像数据结构：
{
  "client_id": "client_123",
  "price_sensitivity": 0.8,      # 价格敏感度
  "time_urgency": 0.5,            # 时间紧急度
  "quality_preference": 0.7,      # 质量偏好
  "brand_preferences": ["Apple"], # 品牌偏好
  "purchase_history": [...]       # 购买历史
}

存储位置：
  • Redis: 实时缓存
  • SQLite: 持久化存储

使用场景：
  1. C端Agent 根据用户画像生成谈判策略
  2. B端Agent 根据用户画像调整报价
  3. 系统根据用户历史推荐商品
```

### B端商家个性化设置

```
商家画像数据结构：
{
  "merchant_id": "merchant_456",
  "shop_name": "电子产品店",
  "pricing_strategy": "normal",   # normal/aggressive/conservative
  "negotiation_style": "friendly", # friendly/strict/flexible
  "service_rating": 4.8,
  "response_speed": 1.0
}

存储位置：
  • Redis: 实时缓存
  • SQLite: 持久化存储

使用场景：
  1. B端Agent 根据商家画像生成报价
  2. 系统根据商家评分推荐给用户
  3. 商家可以调整谈判风格
```

---

## 📊 数据流转流程

### 1️⃣ 用户发起购买

```
C端小程序
  ↓ 用户输入商品和价格
  ↓
后端 API
  ↓ 创建对话会话
  ↓
Redis
  ↓ 缓存会话信息
  ↓
SQLite
  ↓ 记录交易记录
```

### 2️⃣ Agent 对话过程

```
C端Agent
  ↓ 生成谈判策略
  ↓
DeepSeek LLM
  ↓ 生成对话文本
  ↓
B端Agent
  ↓ 生成报价
  ↓
Redis
  ↓ 缓存对话历史
  ↓
SQLite
  ↓ 记录对话轮次
```

### 3️⃣ 订单创建

```
C端用户确认
  ↓
后端 API
  ↓ 创建订单
  ↓
Redis
  ↓ 缓存订单信息
  ↓
SQLite
  ↓ 持久化订单数据
  ↓
B端商家系统
  ↓ 显示新订单
```

---

## 🔄 完整的业务流程

### 第 1 阶段：用户发现

```
C端小程序首页
  ↓
用户浏览商品
  ↓
用户输入想要的商品和预期价格
  ↓
系统加载用户画像
```

### 第 2 阶段：Agent 谈判

```
C端Agent 生成开场白
  ↓
B端Agent 生成初始报价
  ↓
C端用户查看报价
  ↓
用户决定是否继续谈判
  ↓
多轮对话
  ↓
达成协议或放弃
```

### 第 3 阶段：订单创建

```
用户确认最终报价
  ↓
系统创建订单
  ↓
订单保存到数据库
  ↓
B端商家系统显示新订单
  ↓
商家处理订单
```

### 第 4 阶段：订单完成

```
商家发货
  ↓
用户收货
  ↓
用户评价
  ↓
系统更新用户和商家画像
  ↓
为下次购买优化推荐
```

---

## 🚀 启动流程

### 一键启动所有服务

```
.\start_all.ps1
  ↓
选择启动模式
  ↓
启动 Redis（端口 6379）
  ↓
启动后端 API（端口 8765）
  ↓
启动融资路演大屏（端口 8501）
  ↓
启动小程序（微信开发者工具）
  ↓
所有服务就绪
```

### 各服务启动命令

```
后端 API：
  python -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 8765 --reload

融资路演大屏：
  streamlit run cloud_server/god_dashboard.py --server.port 8501

Redis：
  docker run -d -p 6379:6379 redis:latest

小程序：
  微信开发者工具 → 打开项目 → 编译 → 预览
```

---

## 📍 访问地址

```
后端 API：http://localhost:8765
API 文档：http://localhost:8765/docs
融资路演大屏：http://localhost:8501
Redis：localhost:6379
小程序：微信开发者工具模拟器
```

---

## 🔐 安全和可靠性

### 异步处理

```
所有 IO 操作都是异步的：
  • FastAPI 异步路由
  • 异步数据库操作
  • 异步 Redis 操作
  • 异步 LLM 调用
```

### 幂等性保证

```
所有状态变更操作都有幂等键：
  • 交易记录
  • 订单创建
  • 用户画像更新
```

### 数据持久化

```
关键数据都有备份：
  • Redis 缓存
  • SQLite 数据库
  • 审计日志
```

---

## 📊 技术亮点

### 1️⃣ Agent 对话系统
```
✅ C端Agent 和 B端Agent 自动谈判
✅ 基于用户和商家画像的智能定价
✅ 多轮对话直到达成协议
✅ 实时 WebSocket 通信
```

### 2️⃣ 个性化设置
```
✅ 用户价格敏感度
✅ 时间紧急度
✅ 质量偏好
✅ 商家定价策略
✅ 商家谈判风格
```

### 3️⃣ 实时通信
```
✅ WebSocket 实时对话
✅ 完整的对话历史
✅ 最终报价展示
✅ 订单创建
```

### 4️⃣ 生产级别配置
```
✅ Docker 容器化
✅ Railway 自动部署
✅ 完整的错误处理
✅ 详细的日志记录
✅ 一键启动脚本
```

---

## 🎯 核心业务逻辑

### 价格计算逻辑

```
基础价格 = 用户预期价格 * 1.2

商家报价调整：
  if 定价策略 == "aggressive":
    报价 = 基础价格 * 1.1
  elif 定价策略 == "conservative":
    报价 = 基础价格 * 0.95
  else:
    报价 = 基础价格

用户画像调整：
  if 价格敏感度 > 0.7:
    报价 *= 0.95  # 给予折扣

最终报价 = 报价 * 用户画像调整系数
```

### 满意度计算逻辑

```
if 报价 <= 预期价格:
  满意度 = 0.9 + (折扣率 * 0.1)
else:
  满意度 = 1 - (报价 - 预期价格) / 预期价格 * (1 - 时间紧急度)

if 满意度 > 0.6:
  接受报价 = True
else:
  继续谈判
```

---

## 🎉 完整的系统流程

```
用户启动小程序
  ↓
输入商品和价格
  ↓
系统加载用户画像
  ↓
C端Agent 生成开场白
  ↓
B端Agent 生成初始报价
  ↓
用户查看报价
  ↓
多轮对话（WebSocket）
  ↓
达成协议
  ↓
用户确认
  ↓
创建订单
  ↓
B端商家系统显示订单
  ↓
商家处理订单
  ↓
订单完成
  ↓
系统更新用户和商家画像
```

---

## ✅ 项目完成度

```
✅ 后端 API 服务（100%）
✅ 融资路演大屏（100%）
✅ 微信小程序（100%）
✅ Agent 对话系统（100%）
✅ 个性化设置（100%）
✅ 实时通信（100%）
✅ 一键启动脚本（100%）
✅ 完整文档（100%）
✅ Railway 部署（100%）
✅ 所有启动命令集成（100%）

总体完成度：100% ✅
```

---

## 🚀 现在就启动吧！

```powershell
cd "d:\桌面\Project Claw"
.\start_all.ps1
```

选择菜单选项 `1` 启动所有服务！

---

**Project Claw 已完全准备就绪！** 🎉🦞
