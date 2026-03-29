# Project Claw 完整一键启动指南 v1.0

## 🚀 快速启动（推荐）

### Windows PowerShell - 一键启动所有服务

```powershell
# 复制以下命令到 PowerShell 中执行

# 第 1 步：进入项目目录
cd "d:\桌面\Project Claw"

# 第 2 步：激活虚拟环境
venv\Scripts\activate.bat

# 第 3 步：启动所有服务（在后台运行）
# 终端 1：启动后端 API 服务
Start-Process cmd -ArgumentList "/k python -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 8765 --reload"

# 终端 2：启动融资路演大屏
Start-Process cmd -ArgumentList "/k streamlit run cloud_server/god_dashboard.py --server.port 8501"

# 终端 3：启动 Redis（如果已安装 Docker）
Start-Process cmd -ArgumentList "/k docker run -d -p 6379:6379 redis:latest"

# 等待 3 秒让所有服务启动
Start-Sleep -Seconds 3

# 自动打开浏览器
Start-Process "http://localhost:8765/docs"
Start-Process "http://localhost:8501"
```

---

## 📋 分步启动指南

### 方案 A：使用启动脚本（最简单）

#### Windows 批处理脚本
```powershell
# 运行启动脚本
.\start_project.bat
```

#### Linux/macOS 脚本
```bash
# 运行启动脚本
bash start_project.sh
```

---

### 方案 B：手动启动（完全控制）

#### 终端 1：启动后端 API 服务
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

#### 终端 2：启动融资路演大屏
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

#### 终端 3：启动 Redis（可选但推荐）
```powershell
# 方式 1：使用 Docker
docker run -d -p 6379:6379 redis:latest

# 方式 2：使用 Chocolatey
redis-server

# 方式 3：使用 WSL2
wsl redis-server
```

**验证 Redis：**
```powershell
redis-cli ping
# 应该返回：PONG
```

#### 终端 4：启动微信小程序（可选）
```
1. 打开微信开发者工具
2. 打开项目：d:\桌面\Project Claw\miniprogram
3. 点击"编译"或按 Ctrl+Shift+R
4. 在模拟器中预览
```

---

## 🎯 完整的启动流程

### 第 1 步：验证环境（1 分钟）
```powershell
# 检查 Python
python --version
# 应该显示：Python 3.12.7

# 检查虚拟环境
Test-Path "venv"
# 应该返回：True

# 检查数据库
Test-Path "audit.db"
Test-Path "dlq.db"
# 都应该返回：True

# 检查 Redis
docker ps
# 应该看到 redis 容器
```

### 第 2 步：启动后端服务（2 分钟）
```powershell
cd "d:\桌面\Project Claw"
venv\Scripts\activate.bat
python -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 8765 --reload
```

### 第 3 步：启动融资路演大屏（1 分钟）
```powershell
# 新终端
cd "d:\桌面\Project Claw"
venv\Scripts\activate.bat
streamlit run cloud_server/god_dashboard.py --server.port 8501
```

### 第 4 步：启动小程序（1 分钟）
```
微信开发者工具 → 打开项目 → 编译 → 预览
```

**总计：5 分钟启动完整项目**

---

## 📍 启动后可访问的地址

```
后端 API：http://localhost:8765
API 文档：http://localhost:8765/docs
融资路演大屏：http://localhost:8501
Redis：localhost:6379
微信小程序：在微信开发者工具中预览
```

---

## 🔍 验证所有服务

### 检查后端服务
```powershell
curl http://localhost:8765/health
# 应该返回：{"status":"ok"}
```

### 检查融资路演大屏
```powershell
curl http://localhost:8501
# 应该返回 HTML 页面
```

### 检查 Redis
```powershell
redis-cli ping
# 应该返回：PONG
```

### 检查小程序
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

### 方式 3：使用任务管理器
```
Ctrl+Shift+Esc → 找到 python.exe 和 streamlit → 结束任务
```

---

## 📊 启动状态检查清单

- [ ] Python 虚拟环境已激活
- [ ] 后端 API 服务已启动（端口 8765）
- [ ] 融资路演大屏已启动（端口 8501）
- [ ] Redis 已启动（端口 6379）
- [ ] 数据库已初始化（audit.db, dlq.db）
- [ ] 环境变量已配置（.env）
- [ ] DeepSeek API 已配置
- [ ] 小程序已编译
- [ ] 所有服务可访问
- [ ] 控制台无错误

---

## 🎯 快速命令参考

### 最快启动（3 个命令）
```powershell
cd "d:\桌面\Project Claw"
venv\Scripts\activate.bat
python -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 8765 --reload
```

### 完整启动（4 个终端）
```powershell
# 终端 1
python -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 8765 --reload

# 终端 2
streamlit run cloud_server/god_dashboard.py --server.port 8501

# 终端 3
docker run -d -p 6379:6379 redis:latest

# 终端 4
微信开发者工具 → 编译
```

### 验证所有服务
```powershell
curl http://localhost:8765/health
curl http://localhost:8501
redis-cli ping
```

---

## 💡 常见问题

### Q1：如何快速重启所有服务？
```powershell
# 关闭所有 Python 进程
Stop-Process -Name python -Force

# 重新启动
python -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 8765 --reload
```

### Q2：如何查看实时日志？
```powershell
# 后端日志在启动的终端中显示
# 融资路演大屏日志在启动的终端中显示
# 小程序日志在微信开发者工具控制台中显示
```

### Q3：如何修改端口？
```powershell
# 后端端口（默认 8765）
python -m uvicorn cloud_server.api_server_pro:app --port 9000

# 融资路演大屏端口（默认 8501）
streamlit run cloud_server/god_dashboard.py --server.port 9001

# Redis 端口（默认 6379）
docker run -d -p 9379:6379 redis:latest
```

### Q4：如何在后台运行？
```powershell
# 使用 nohup（Linux/macOS）
nohup python -m uvicorn cloud_server.api_server_pro:app &

# 使用 Start-Process（Windows）
Start-Process python -ArgumentList "-m uvicorn cloud_server.api_server_pro:app"
```

---

## 📚 相关文档

```
快速启动指南：QUICK_START_GUIDE.md
完整检查报告：COMPLETE_ENVIRONMENT_CHECK_REPORT.md
小程序改善方案：MINIPROGRAM_IMPROVEMENT_PLAN.md
Railway 修复指南：RAILWAY_FIX_GUIDE.md
```

---

## ✅ 最终检查清单

- [x] 后端 API 服务配置完成
- [x] 融资路演大屏配置完成
- [x] Redis 配置完成
- [x] 小程序配置完成
- [x] 环境变量配置完成
- [x] 数据库初始化完成
- [ ] 启动所有服务
- [ ] 验证所有服务
- [ ] 开始开发

---

## 🎉 现在就启动吧！

**最简单的方式：**
```powershell
cd "d:\桌面\Project Claw"
venv\Scripts\activate.bat
python -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 8765 --reload
```

**然后在新终端：**
```powershell
streamlit run cloud_server/god_dashboard.py --server.port 8501
```

**访问：**
```
http://localhost:8765/docs
http://localhost:8501
```

---

**祝你使用愉快！** 🚀🦞
