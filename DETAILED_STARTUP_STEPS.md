# Project Claw 完整项目启动详细操作步骤

## 🚀 快速启动（推荐）- 5 分钟内启动所有服务

### 第 1 步：打开 PowerShell
```
1. 按 Win + X
2. 选择 "Windows PowerShell (管理员)"
3. 或直接搜索 "PowerShell" 并以管理员身份运行
```

### 第 2 步：进入项目目录
```powershell
cd "d:\桌面\Project Claw"
```

### 第 3 步：运行一键启动脚本
```powershell
.\start_all.ps1
```

### 第 4 步：选择启动模式
```
选择启动模式：
  1. 🚀 启动所有服务（推荐）
  2. 🔧 仅启动后端 API
  3. 📊 仅启动融资路演大屏
  4. 💾 仅启动 Redis
  5. 📱 仅启动小程序
  6. 🔄 启动后端 + 大屏 + Redis
  0. ❌ 退出

请选择 (0-6): 1
```

**输入 `1` 然后按 Enter**

### 第 5 步：等待所有服务启动
```
预期输出：
✓ Redis 容器已启动（端口 6379）
✓ 后端 API 已启动（端口 8765）
✓ 融资路演大屏已启动（端口 8501）
✓ 打开浏览器
```

### 第 6 步：访问各个服务
```
后端 API 文档：http://localhost:8765/docs
融资路演大屏：http://localhost:8501
小程序：微信开发者工具（见下文）
```

---

## 📋 详细的分步启动（完全控制）

### 方式 1：手动启动所有服务（4 个终端）

#### 终端 1：启动 Redis 缓存服务

**第 1 步：打开第一个 PowerShell**
```
按 Win + X → 选择 "Windows PowerShell (管理员)"
```

**第 2 步：启动 Redis**
```powershell
docker run -d -p 6379:6379 redis:latest
```

**预期输出：**
```
[容器 ID]
```

**第 3 步：验证 Redis 运行**
```powershell
redis-cli ping
```

**预期输出：**
```
PONG
```

---

#### 终端 2：启动后端 API 服务

**第 1 步：打开第二个 PowerShell**
```
按 Win + X → 选择 "Windows PowerShell (管理员)"
```

**第 2 步：进入项目目录**
```powershell
cd "d:\桌面\Project Claw"
```

**第 3 步：激活虚拟环境**
```powershell
venv\Scripts\activate.bat
```

**预期输出：**
```
(venv) PS d:\桌面\Project Claw>
```

**第 4 步：启动后端 API**
```powershell
python -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 8765 --reload
```

**预期输出：**
```
INFO:     Uvicorn running on http://0.0.0.0:8765
INFO:     Application startup complete
```

**第 5 步：验证后端 API**
```
在浏览器中访问：http://localhost:8765/docs
应该看到 Swagger API 文档
```

---

#### 终端 3：启动融资路演大屏

**第 1 步：打开第三个 PowerShell**
```
按 Win + X → 选择 "Windows PowerShell (管理员)"
```

**第 2 步：进入项目目录**
```powershell
cd "d:\桌面\Project Claw"
```

**第 3 步：激活虚拟环境**
```powershell
venv\Scripts\activate.bat
```

**第 4 步：启动融资路演大屏**
```powershell
streamlit run cloud_server/god_dashboard.py --server.port 8501
```

**预期输出：**
```
You can now view your Streamlit app in your browser.
Local URL: http://localhost:8501
```

**第 5 步：验证融资路演大屏**
```
在浏览器中访问：http://localhost:8501
应该看到融资路演大屏
```

---

#### 微信开发者工具：启动小程序

**第 1 步：打开微信开发者工具**
```
1. 下载并安装微信开发者工具
   https://developers.weixin.qq.com/community/develop/tools/download
2. 打开微信开发者工具
```

**第 2 步：打开项目**
```
1. 点击"打开"
2. 选择项目路径：d:\桌面\Project Claw\miniprogram
3. 点击"打开"
```

**第 3 步：编译项目**
```
1. 点击"编译"或按 Ctrl+Shift+R
2. 等待编译完成
```

**第 4 步：预览小程序**
```
1. 在模拟器中查看小程序
2. 应该看到小程序首页
```

---

## 🎯 各服务详细说明

### 1️⃣ Redis 缓存服务（端口 6379）

**功能：**
- 缓存用户画像
- 缓存对话历史
- 缓存订单信息
- 缓存会话数据

**启动命令：**
```powershell
docker run -d -p 6379:6379 redis:latest
```

**验证命令：**
```powershell
redis-cli ping
# 返回：PONG
```

**停止命令：**
```powershell
docker stop $(docker ps -q --filter ancestor=redis:latest)
```

---

### 2️⃣ 后端 API 服务（端口 8765）

**功能：**
- 处理 C端小程序请求
- 处理 B端商家系统请求
- 管理 Agent 对话
- 管理用户和商家画像
- 管理订单和交易

**启动命令：**
```powershell
python -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 8765 --reload
```

**访问地址：**
```
API 文档：http://localhost:8765/docs
健康检查：http://localhost:8765/health
```

**主要路由：**
```
POST   /a2a/dialogue/start              # 启动对话
POST   /a2a/dialogue/continue           # 继续对话
GET    /a2a/dialogue/{session_id}       # 获取会话
GET    /a2a/dialogue/{session_id}/history # 获取历史
WS     /a2a/dialogue/ws/{session_id}    # WebSocket 实时对话
POST   /a2a/dialogue/profile/client     # 保存用户画像
POST   /a2a/dialogue/profile/merchant   # 保存商家画像
GET    /health                          # 健康检查
GET    /docs                            # Swagger API 文档
```

**停止命令：**
```powershell
Stop-Process -Name python -Force
```

---

### 3️⃣ 融资路演大屏（端口 8501）

**功能：**
- B端商家系统
- 显示实时数据
- 显示对话历史
- 显示订单管理
- 显示商家管理
- 显示数据分析

**启动命令：**
```powershell
streamlit run cloud_server/god_dashboard.py --server.port 8501
```

**访问地址：**
```
融资路演大屏：http://localhost:8501
```

**页面：**
- 首页：实时数据展示
- 对话管理：查看所有对话
- 订单管理：查看所有订单
- 商家管理：管理商家信息
- 数据分析：数据统计和分析

**停止命令：**
```powershell
Stop-Process -Name streamlit -Force
```

---

### 4️⃣ 微信小程序

**功能：**
- C端用户系统
- 发现页面：搜索商品
- 对话页面：与 Agent 谈判
- 订单页面：查看订单
- 商家页面：浏览商家
- 个性化设置：调整谈判策略

**启动方式：**
```
微信开发者工具 → 打开项目 → 编译 → 预览
```

**项目路径：**
```
d:\桌面\Project Claw\miniprogram
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

## ✅ 启动检查清单

启动前：
- [ ] 进入项目目录：`cd "d:\桌面\Project Claw"`
- [ ] 激活虚拟环境：`venv\Scripts\activate.bat`
- [ ] 检查 Docker 是否运行
- [ ] 检查端口是否被占用

启动后：
- [ ] 后端 API 运行正常（http://localhost:8765）
- [ ] 融资路演大屏运行正常（http://localhost:8501）
- [ ] Redis 连接正常（localhost:6379）
- [ ] 小程序可以连接
- [ ] 没有错误信息

---

## 💡 常见问题和解决方案

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
1. 下载 Docker Desktop：https://www.docker.com/products/docker-desktop
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

查看占用端口的进程：
netstat -ano | findstr :8765
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

### Q5：虚拟环境激活失败
```
错误：无法激活虚拟环境

解决：
1. 检查虚拟环境是否存在：ls venv
2. 如果不存在，创建虚拟环境：python -m venv venv
3. 重新激活：venv\Scripts\activate.bat
```

---

## 📊 完整的启动流程图

```
第 1 步：打开 PowerShell
    ↓
第 2 步：进入项目目录
    ↓
第 3 步：运行一键启动脚本
    ↓
第 4 步：选择启动模式（选择 1）
    ↓
第 5 步：等待所有服务启动
    ↓
第 6 步：访问各个服务
    ↓
第 7 步：开始开发
```

---

## 🎉 现在就启动吧！

### 最简单的方式（推荐）
```powershell
cd "d:\桌面\Project Claw"
.\start_all.ps1
# 选择 1
```

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
完整启动指南：COMPLETE_STARTUP_GUIDE.md
一键启动脚本：start_all.ps1
启动脚本指南：START_ALL_GUIDE.md
完整启动命令：ALL_STARTUP_COMMANDS.md
完整技术总结：COMPLETE_TECHNICAL_SUMMARY.md
深度优化方案：PROJECT_DEEP_OPTIMIZATION_V1.md
```

---

**Project Claw 已完全准备就绪！** 🎉🦞

按照上述步骤启动你的项目，所有服务都会正常运行。

现在就开始吧！
