# Project Claw C端Agent + B端Agent 对话系统完整实现指南

## 🏗️ 系统架构

```
C 端小程序 (WeChat Mini Program)
    ↓ WebSocket
Agent 对话系统 (FastAPI)
    ↓ HTTP/WebSocket
B 端商家系统 (Streamlit Dashboard)
    ↓ 共享数据库
个性化设置存储 (Redis + SQLite)
```

---

## 📱 C 端小程序运行环境

### 文件位置
```
d:\桌面\Project Claw\miniprogram\
├── pages/
│   └── dialogue/
│       ├── dialogue.js          # 对话页面
│       ├── dialogue_agent.js    # Agent对话页面（新）
│       ├── dialogue.wxml
│       └── dialogue.wxss
├── api/
│   └── request.js               # API请求模块
└── utils/
    └── profile.js               # 用户画像管理
```

### 启动方式
```
1. 打开微信开发者工具
2. 打开项目：d:\桌面\Project Claw\miniprogram
3. 点击"编译"或按 Ctrl+Shift+R
4. 在模拟器中预览
```

### 访问地址
```
微信开发者工具模拟器
```

---

## 🤖 Agent 对话系统运行环境

### 文件位置
```
d:\桌面\Project Claw\cloud_server\
├── agent_dialogue_service.py    # Agent对话服务（新）
├── agent_dialogue_routes.py     # API路由（新）
├── api_server_pro.py            # FastAPI主服务
└── god_dashboard.py             # B端商家系统
```

### 启动方式
```powershell
cd "d:\桌面\Project Claw"
venv\Scripts\activate.bat
python -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 8765 --reload
```

### 访问地址
```
后端 API：http://localhost:8765
API 文档：http://localhost:8765/docs
WebSocket：ws://localhost:8765/a2a/dialogue/ws/{session_id}
```

---

## 🏪 B 端商家系统运行环境

### 文件位置
```
d:\桌面\Project Claw\cloud_server\
└── god_dashboard.py             # Streamlit 融资路演大屏
```

### 启动方式
```powershell
cd "d:\桌面\Project Claw"
venv\Scripts\activate.bat
streamlit run cloud_server/god_dashboard.py --server.port 8501
```

### 访问地址
```
http://localhost:8501
```

---

## 💬 C端Agent 和 B端Agent 对话流程

### 1. 启动对话

**C端小程序发起：**
```javascript
// 调用 API 启动对话
POST /a2a/dialogue/start
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
```

**返回：**
```json
{
  "session_id": "session_abc123",
  "status": "active",
  "turns": [
    {
      "turn_id": 0,
      "speaker": "client_agent",
      "text": "我想要一部iPhone 15，预算5000元"
    },
    {
      "turn_id": 1,
      "speaker": "merchant_agent",
      "text": "我们有iPhone 15，现在价格是5800元"
    }
  ]
}
```

### 2. 实时对话（WebSocket）

**C端小程序连接：**
```javascript
// 连接 WebSocket
ws://localhost:8765/a2a/dialogue/ws/session_abc123

// 接收对话历史
{
  "type": "history",
  "turns": [...]
}

// 继续对话
ws.send({
  "type": "continue",
  "session_id": "session_abc123",
  "max_turns": 5
})

// 接收更新
{
  "type": "update",
  "status": "completed",
  "turns": [...],
  "best_offer": {
    "price": 4800,
    "satisfaction": 0.85
  }
}
```

### 3. 对话完成

**最终结果：**
```json
{
  "session_id": "session_abc123",
  "status": "completed",
  "best_offer": {
    "price": 4800,
    "satisfaction": 0.85
  },
  "turns": [
    // 完整的对话历史
  ]
}
```

---

## 🎯 个性化设置实现

### C端用户个性化设置

**保存用户画像：**
```
POST /a2a/dialogue/profile/client
{
  "client_id": "client_123",
  "price_sensitivity": 0.8,      # 价格敏感度（0-1）
  "time_urgency": 0.5,            # 时间紧急度（0-1）
  "quality_preference": 0.7,      # 质量偏好（0-1）
  "brand_preferences": ["Apple"], # 品牌偏好
  "purchase_history": [...]       # 购买历史
}
```

**获取用户画像：**
```
GET /a2a/dialogue/profile/client/client_123
```

### B端商家个性化设置

**保存商家画像：**
```
POST /a2a/dialogue/profile/merchant
{
  "merchant_id": "merchant_456",
  "shop_name": "电子产品店",
  "pricing_strategy": "normal",   # normal, aggressive, conservative
  "negotiation_style": "friendly", # friendly, strict, flexible
  "service_rating": 4.8,
  "response_speed": 1.0
}
```

**获取商家画像：**
```
GET /a2a/dialogue/profile/merchant/merchant_456
```

---

## 🔧 集成步骤

### 第 1 步：在 FastAPI 中注册路由

编辑 `cloud_server/api_server_pro.py`：

```python
from .agent_dialogue_routes import router as dialogue_router

app = FastAPI()

# 注册对话路由
app.include_router(dialogue_router)
```

### 第 2 步：在小程序中使用对话

编辑 `miniprogram/pages/index/index.js`：

```javascript
async onStartAgentDialogue() {
  const app = getApp();
  const dialogueAPI = DialogueAPI(this._request);
  
  // 启动 Agent 对话
  const res = await dialogueAPI.startAutoNegotiation({
    clientId: app.globalData.clientId,
    itemName: this.data.itemName,
    expectedPrice: this.data.expectedPrice,
    clientProfile: this.data.profile,
  });
  
  // 跳转到对话页面
  wx.navigateTo({
    url: `/pages/dialogue/dialogue_agent?sessionId=${res.session_id}&itemName=${this.data.itemName}`,
  });
}
```

### 第 3 步：在 B端商家系统中显示对话

编辑 `cloud_server/god_dashboard.py`：

```python
import streamlit as st
import requests

# 获取对话会话
session_id = st.text_input("输入会话 ID")

if session_id:
    response = requests.get(f"http://localhost:8765/a2a/dialogue/{session_id}")
    session = response.json()
    
    st.write("### 对话历史")
    for turn in session["turns"]:
        if turn["speaker"] == "client_agent":
            st.write(f"**客户**: {turn['text']}")
        else:
            st.write(f"**商家**: {turn['text']}")
    
    if session["best_offer"]:
        st.success(f"最终报价: ¥{session['best_offer']['price']}")
```

---

## 📊 完整的启动流程

### 终端 1：启动后端 API
```powershell
cd "d:\桌面\Project Claw"
venv\Scripts\activate.bat
python -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 8765 --reload
```

### 终端 2：启动 B端商家系统
```powershell
cd "d:\桌面\Project Claw"
venv\Scripts\activate.bat
streamlit run cloud_server/god_dashboard.py --server.port 8501
```

### 微信开发者工具：启动 C端小程序
```
打开项目 → 编译 → 预览
```

---

## 🎯 测试流程

### 1. 在小程序中输入商品信息
```
商品名：iPhone 15
预期价格：5000
```

### 2. 点击"Agent自动谈判"
```
小程序 → 启动 Agent 对话 → 跳转到对话页面
```

### 3. 查看实时对话
```
C端Agent 和 B端Agent 自动进行对话
显示对话历史和最终报价
```

### 4. 在 B端商家系统中查看
```
访问 http://localhost:8501
输入会话 ID
查看完整的对话历史
```

---

## 📍 API 端点总结

### 对话管理
```
POST   /a2a/dialogue/start              # 启动对话
POST   /a2a/dialogue/continue           # 继续对话
GET    /a2a/dialogue/{session_id}       # 获取会话
GET    /a2a/dialogue/{session_id}/history # 获取历史
```

### 个性化设置
```
POST   /a2a/dialogue/profile/client     # 保存用户画像
POST   /a2a/dialogue/profile/merchant   # 保存商家画像
GET    /a2a/dialogue/profile/client/{id}    # 获取用户画像
GET    /a2a/dialogue/profile/merchant/{id}  # 获取商家画像
```

### WebSocket
```
WS     /a2a/dialogue/ws/{session_id}    # 实时对话连接
```

---

## 💡 关键特性

### ✅ C端Agent
- 根据用户画像生成谈判策略
- 自动评估商家报价
- 支持多轮谈判
- 实时反馈

### ✅ B端Agent
- 根据商家画像生成报价
- 支持不同的定价策略
- 自动响应客户反价
- 灵活的谈判风格

### ✅ 个性化设置
- 用户价格敏感度
- 时间紧急度
- 质量偏好
- 商家定价策略
- 商家谈判风格

### ✅ 实时通信
- WebSocket 实时对话
- 完整的对话历史
- 最终报价展示
- 订单创建

---

## 🚀 现在就试试吧！

**一键启动所有服务：**
```powershell
.\one_click_startup.ps1
```

**然后：**
1. 打开小程序
2. 输入商品信息
3. 点击"Agent自动谈判"
4. 查看实时对话
5. 接受最终报价

---

**祝你使用愉快！** 🎉🦞
