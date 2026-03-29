# Project Claw 完整启动命令汇总 v1.0

## 🚀 一键启动所有服务（推荐）

### Windows PowerShell
```powershell
cd "d:\桌面\Project Claw"
.\one_click_startup.ps1
```

**自动完成：**
- ✅ 验证环境
- ✅ 激活虚拟环境
- ✅ 启动 Redis
- ✅ 启动后端 API
- ✅ 启动融资路演大屏
- ✅ 打开浏览器

---

## 📋 分步启动命令

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

### 第 6 步：启动小程序（微信开发者工具）
```
1. 打开微信开发者工具
2. 打开项目：d:\桌面\Project Claw\miniprogram
3. 点击"编译"或按 Ctrl+Shift+R
4. 在模拟器中预览
```

---

## 🎯 快速启动命令参考

### 仅启动后端 API
```powershell
cd "d:\桌面\Project Claw"
venv\Scripts\activate.bat
python -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 8765 --reload
```

### 仅启动融资路演大屏
```powershell
cd "d:\桌面\Project Claw"
venv\Scripts\activate.bat
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

## 📍 启动后可访问的地址

```
后端 API：http://localhost:8765
API 文档：http://localhost:8765/docs
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

### 方式 3：使用任务管理器
```
Ctrl+Shift+Esc → 找到 python.exe 和 streamlit → 结束任务
```

---

## 📊 完整的启动流程（手动）

### 终端 1：启动后端 API
```powershell
cd "d:\桌面\Project Claw"
venv\Scripts\activate.bat
python -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 8765 --reload
```

### 终端 2：启动融资路演大屏
```powershell
cd "d:\桌面\Project Claw"
venv\Scripts\activate.bat
streamlit run cloud_server/god_dashboard.py --server.port 8501
```

### 终端 3：启动 Redis
```powershell
docker run -d -p 6379:6379 redis:latest
```

### 微信开发者工具：启动小程序
```
打开项目 → 编译 → 预览
```

---

## 🎯 按功能分类的启动命令

### 开发环境启动
```powershell
# 后端开发
python -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 8765 --reload

# 大屏开发
streamlit run cloud_server/god_dashboard.py --server.port 8501

# 小程序开发
微信开发者工具 → 编译
```

### 生产环境启动
```powershell
# 后端生产
python -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 8765 --workers 4

# 大屏生产
streamlit run cloud_server/god_dashboard.py --server.port 8501 --logger.level=warning

# 小程序生产
微信小程序发布
```

### 测试环境启动
```powershell
# 运行单元测试
pytest tests/ -v

# 运行集成测试
pytest tests/integration/ -v

# 运行覆盖率测试
pytest tests/ --cov=cloud_server --cov-report=html
```

---

## 💡 常用命令组合

### 快速开发启动（3 个终端）
```
终端 1：python -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 8765 --reload
终端 2：streamlit run cloud_server/god_dashboard.py --server.port 8501
终端 3：docker run -d -p 6379:6379 redis:latest
```

### 最小化启动（仅后端）
```powershell
python -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 8765 --reload
```

### 完整启动（所有服务）
```powershell
.\one_click_startup.ps1
```

---

## 🔧 自定义启动命令

### 修改后端端口
```powershell
python -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 9000 --reload
```

### 修改大屏端口
```powershell
streamlit run cloud_server/god_dashboard.py --server.port 9001
```

### 修改 Redis 端口
```powershell
docker run -d -p 9379:6379 redis:latest
```

### 启用调试模式
```powershell
python -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 8765 --reload --log-level debug
```

### 禁用自动重载
```powershell
python -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 8765
```

---

## 📝 启动命令速查表

| 服务 | 命令 | 端口 | 说明 |
|------|------|------|------|
| 后端 API | `python -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 8765 --reload` | 8765 | FastAPI 服务器 |
| 融资路演大屏 | `streamlit run cloud_server/god_dashboard.py --server.port 8501` | 8501 | Streamlit 应用 |
| Redis | `docker run -d -p 6379:6379 redis:latest` | 6379 | 缓存服务 |
| 小程序 | 微信开发者工具编译 | - | WeChat Mini Program |
| 一键启动 | `.\one_click_startup.ps1` | 多个 | 启动所有服务 |

---

## ✅ 启动检查清单

启动前：
- [ ] 进入项目目录
- [ ] 激活虚拟环境
- [ ] 检查 Redis 是否运行
- [ ] 检查端口是否被占用

启动后：
- [ ] 后端 API 运行正常
- [ ] 融资路演大屏运行正常
- [ ] Redis 连接正常
- [ ] 小程序可以连接
- [ ] 没有错误信息

---

## 🎉 现在就启动吧！

**最简单的方式：**
```powershell
.\one_click_startup.ps1
```

**或手动启动：**
```powershell
# 终端 1
python -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 8765 --reload

# 终端 2
streamlit run cloud_server/god_dashboard.py --server.port 8501

# 终端 3
docker run -d -p 6379:6379 redis:latest
```

**然后访问：**
- http://localhost:8765/docs
- http://localhost:8501
- 微信开发者工具

---

**祝你使用愉快！** 🚀🦞
