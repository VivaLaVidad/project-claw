# Project Claw 完整项目启动指南

## 🚀 最快启动方式（一键启动所有）

### 方式 1：使用一键启动脚本（推荐）
```powershell
cd "d:\桌面\Project Claw"
.\start_all.ps1
```

然后选择菜单选项 `1` 启动所有服务

**自动启动：**
- ✅ Redis 缓存服务（端口 6379）
- ✅ 后端 API 服务（端口 8765）
- ✅ 融资路演大屏（端口 8501）
- ✅ 打开浏览器

---

## 📋 分步启动指南（完全控制）

### 第 1 步：进入项目目录
```powershell
cd "d:\桌面\Project Claw"
```

### 第 2 步：激活虚拟环境
```powershell
venv\Scripts\activate.bat
```

### 第 3 步：启动 Redis（新终端）
```powershell
docker run -d -p 6379:6379 redis:latest
```

**验证 Redis：**
```powershell
redis-cli ping
# 应该返回：PONG
```

### 第 4 步：启动后端 API 服务（新终端）
```powershell
cd "d:\桌面\Project Claw"
venv\Scripts\activate.bat
python -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 8765 --reload
```

**预期输出：**
```
INFO:     Uvicorn running on http://0.0.0.0:8765
INFO:     Application startup complete
```

**访问：**
- 后端 API：http://localhost:8765
- API 文档：http://localhost:8765/docs

### 第 5 步：启动融资路演大屏（新终端）
```powershell
cd "d:\桌面\Project Claw"
venv\Scripts\activate.bat
streamlit run cloud_server/god_dashboard.py --server.port 8501
```

**预期输出：**
```
You can now view your Streamlit app in your browser.
Local URL: http://localhost:8501
```

**访问：**
- 融资路演大屏：http://localhost:8501

### 第 6 步：启动微信小程序（微信开发者工具）
```
1. 打开微信开发者工具
2. 打开项目：d:\桌面\Project Claw\miniprogram
3. 点击"编译"或按 Ctrl+Shift+R
4. 在模拟器中预览
```

**预期输出：**
```
[App] ✓ 服务器连接成功
[Index] ✓ 服务器在线
```

---

## 🎯 各组件详细启动说明

### 1️⃣ Redis 缓存服务

**启动命令：**
```powershell
docker run -d -p 6379:6379 redis:latest
```

**功能：**
- 缓存用户画像
- 缓存对话历史
- 缓存订单信息
- 缓存会话数据

**验证：**
```powershell
redis-cli ping
# 返回：PONG
```

**停止：**
```powershell
docker stop $(docker ps -q --filter ancestor=redis:latest)
```

---

### 2️⃣ 后端 API 服务

**启动命令：**
```powershell
python -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 8765 --reload
```

**功能：**
- 处理 C端小程序请求
- 处理 B端商家系统请求
- 管理 Agent 对话
- 管理用户和商家画像
- 管理订单和交易

**主要路由：**

#### 对话管理
```
POST   /a2a/dialogue/start              # 启动对话
POST   /a2a/dialogue/continue           # 继续对话
GET    /a2a/dialogue/{session_id}       # 获取会话
GET    /a2a/dialogue/{session_id}/history # 获取历史
WS     /a2a/dialogue/ws/{session_id}    # WebSocket 实时对话
```

#### 个性化设置
```
POST   /a2a/dialogue/profile/client     # 保存用户画像
POST   /a2a/dialogue/profile/merchant   # 保存商家画像
GET    /a2a/dialogue/profile/client/{id}    # 获取用户画像
GET    /a2a/dialogue/profile/merchant/{id}  # 获取商家画像
```

#### 系统接口
```
GET    /health                          # 健康检查
GET    /docs                            # Swagger API 文档
GET    /stats                           # 系统统计
```

**访问：**
- API 文档：http://localhost:8765/docs
- 健康检查：http://localhost:8765/health

**停止：**
```powershell
Stop-Process -Name python -Force
```

---

### 3️⃣ 融资路演大屏（B端商家系统）

**启动命令：**
```powershell
streamlit run cloud_server/god_dashboard.py --server.port 8501
```

**功能：**
- 显示实时数据
- 显示对话历史
- 显示订单管理
- 显示商家管理
- 显示数据分析

**页面：**
- 首页：实时数据展示
- 对话管理：查看所有对话
- 订单管理：查看所有订单
- 商家管理：管理商家信息
- 数据分析：数据统计和分析

**访问：**
- 融资路演大屏：http://localhost:8501

**停止：**
```powershell
Stop-Process -Name streamlit -Force
```

---

### 4️⃣ 微信小程序（C端用户系统）

**启动方式：**
```
微信开发者工具 → 打开项目 → 编译 → 预览
```

**项目路径：**
```
d:\桌面\Project Claw\miniprogram
```

**功能：**
- 发现页面：搜索商品
- 对话页面：与 Agent 谈判
- 订单页面：查看订单
- 商家页面：浏览商家
- 个性化设置：调整谈判策略

**页面结构：**
```
miniprogram/
├── pages/
│   ├── index/           # 发现页面
│   ├── dialogue/        # 对话页面
│   ├── orders/          # 订单页面
│   └── merchant/        # 商家页面
├── api/
│   └── request.js       # API 请求模块
├── utils/
│   └── profile.js       # 用户画像管理
└── app.js               # 小程序入口
```

**访问：**
- 微信开发者工具模拟器

---

## 📊 完整的启动流程（手动）

### 终端 1：启动 Redis
```powershell
docker run -d -p 6379:6379 redis:latest
```

### 终端 2：启动后端 API
```powershell
cd "d:\桌面\Project Claw"
venv\Scripts\activate.bat
python -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 8765 --reload
```

### 终端 3：启动融资路演大屏
```powershell
cd "d:\桌面\Project Claw"
venv\Scripts\activate.bat
streamlit run cloud_server/god_dashboard.py --server.port 8501
```

### 微信开发者工具：启动小程序
```
打开项目 → 编译 → 预览
```

---

## 📍 所有访问地址

```
后端 API：http://localhost:8765
API 文档：http://localhost:8765/docs
健康检查：http://localhost:8765/health

融资路演大屏：http://localhost:8501

Redis：localhost:6379

小程序：微信开发者工具模拟器
```

---

## 🔍 验证所有服务

### 验证后端 API
```powershell
curl http://localhost:8765/health
# 应该返回：{"status":"ok"}
```

### 验证融资路演大屏
```powershell
curl http://localhost:8501
# 应该返回 HTML 页面
```

### 验证 Redis
```powershell
redis-cli ping
# 应该返回：PONG
```

### 验证小程序
```
微信开发者工具控制台应该显示：
[App] ✓ 服务器连接成功
[Index] ✓ 服务器在线
```

---

## 🛑 停止所有服务

### 方式 1：关闭终端窗口
```
关闭所有启动的命令行窗口
```

### 方式 2：使用 PowerShell 命令
```powershell
# 停止所有 Python 进程
Stop-Process -Name python -Force

# 停止所有 streamlit 进程
Stop-Process -Name streamlit -Force

# 停止 Redis 容器
docker stop $(docker ps -q --filter ancestor=redis:latest)
```

---

## 🎯 快速启动命令参考

### 最快启动（一键）
```powershell
.\start_all.ps1
```

### 仅启动后端 API
```powershell
python -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 8765 --reload
```

### 仅启动融资路演大屏
```powershell
streamlit run cloud_server/god_dashboard.py --server.port 8501
```

### 仅启动 Redis
```powershell
docker run -d -p 6379:6379 redis:latest
```

### 仅启动小程序
```
微信开发者工具 → 打开项目 → 编译
```

---

## 📊 启动检查清单

启动前：
- [ ] 进入项目目录
- [ ] 激活虚拟环境
- [ ] 检查 Redis 是否运行
- [ ] 检查端口是否被占用

启动后：
- [ ] 后端 API 运行正常（http://localhost:8765）
- [ ] 融资路演大屏运行正常（http://localhost:8501）
- [ ] Redis 连接正常（localhost:6379）
- [ ] 小程序可以连接
- [ ] 没有错误信息

---

## 💡 常见问题

### Q1：脚本无法执行
```
错误：无法加载文件 start_all.ps1

解决：
1. 以管理员身份打开 PowerShell
2. 运行：Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
3. 输入 Y 确认
4. 重新运行脚本
```

### Q2：Docker 未安装
```
错误：Docker 未安装或未运行

解决：
1. 下载 Docker Desktop
2. 安装并启动 Docker Desktop
3. 重新运行脚本
```

### Q3：端口被占用
```
错误：Address already in use

解决：
1. 检查是否已有服务在运行
2. 修改端口号
3. 或关闭占用端口的程序
```

### Q4：小程序无法连接
```
错误：服务器连接失败

解决：
1. 检查后端 API 是否运行
2. 检查 API 地址是否正确
3. 检查防火墙设置
4. 重新编译小程序
```

---

## 🎉 现在就启动吧！

### 最简单的方式
```powershell
cd "d:\桌面\Project Claw"
.\start_all.ps1
```

选择菜单选项 `1` 启动所有服务！

### 或手动启动（4 个终端）
```
终端 1：docker run -d -p 6379:6379 redis:latest
终端 2：python -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 8765 --reload
终端 3：streamlit run cloud_server/god_dashboard.py --server.port 8501
微信开发者工具：打开项目 → 编译 → 预览
```

### 然后访问
```
后端 API 文档：http://localhost:8765/docs
融资路演大屏：http://localhost:8501
小程序：微信开发者工具模拟器
```

---

## 📚 相关文档

```
完整技术总结：COMPLETE_TECHNICAL_SUMMARY.md
一键启动脚本：start_all.ps1
启动脚本指南：START_ALL_GUIDE.md
完整启动命令：ALL_STARTUP_COMMANDS.md
Agent对话完整指南：AGENT_DIALOGUE_COMPLETE_GUIDE.md
```

---

**Project Claw 已完全准备就绪！** 🎉🦞

所有组件都可以一键启动或分步启动。

现在就开始你的项目吧！
