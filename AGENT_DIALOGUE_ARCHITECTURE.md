# Project Claw C端小程序 + B端商家系统 + Agent对话完整实现指南

## 🏗️ 架构概览

```
C 端小程序 (WeChat Mini Program)
    ↓ WebSocket
Agent 对话系统 (Edge Box)
    ↓ HTTP/WebSocket
B 端商家系统 (Web Dashboard)
    ↓ 共享数据库
个性化设置存储 (Redis + SQLite)
```

---

## 📱 第一部分：C 端小程序运行环境

### 运行位置
```
文件位置：d:\桌面\Project Claw\miniprogram\
运行环境：微信开发者工具
端口：无（通过 WebSocket 连接到后端）
```

### 启动方式
```
1. 打开微信开发者工具
2. 打开项目：d:\桌面\Project Claw\miniprogram
3. 点击"编译"或按 Ctrl+Shift+R
4. 在模拟器中预览
```

---

## 🏪 第二部分：B 端商家系统运行环境

### 运行位置
```
文件位置：d:\桌面\Project Claw\cloud_server\
运行环境：Streamlit
端口：8501
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

## 🤖 第三部分：Agent 对话系统

### 运行位置
```
文件位置：d:\桌面\Project Claw\edge_box\
运行环境：FastAPI 后端
端口：8765
```

### 启动方式
```powershell
cd "d:\桌面\Project Claw"
venv\Scripts\activate.bat
python -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 8765 --reload
```

### 访问地址
```
http://localhost:8765
WebSocket：ws://localhost:8765/ws/a2a/client/{clientId}
```

---

## 💬 第四部分：C端Agent 和 B端Agent 对话实现

### 对话流程
```
C 端用户
    ↓ 发送消息
C 端 Agent (LLM)
    ↓ 谈判策略
B 端 Agent (LLM)
    ↓ 商家响应
B 端商家系统
    ↓ 显示对话
C 端小程序
    ↓ 显示结果
```

---

## 🎯 第五部分：个性化设置实现

### 个性化维度
```
C 端用户画像：
- 价格敏感度 (0-1)
- 时间紧急度 (0-1)
- 质量偏好 (0-1)
- 品牌偏好 (list)
- 历史购买记录

B 端商家画像：
- 商品库存
- 定价策略
- 服务评分
- 响应速度
- 谈判风格
```

---

## 📝 代码实现

### 见下面的具体代码文件
