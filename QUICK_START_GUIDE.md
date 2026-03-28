# 🚀 Project Claw 快速启动指南

## ⚡ 一键完整配置（推荐）

### Windows PowerShell
```powershell
# 1. 打开 PowerShell（以管理员身份）
# 2. 进入项目目录
cd d:\桌面\Project Claw

# 3. 允许执行脚本（首次需要）
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# 4. 运行完整配置脚本
.\complete_setup.ps1
```

**脚本会自动完成：**
- ✅ 创建虚拟环境
- ✅ 安装所有依赖
- ✅ 初始化数据库
- ✅ 安装 Redis
- ✅ 启动所有服务
- ✅ 打开浏览器

---

## 📍 启动后的服务地址

```
后端 API：http://localhost:8765
API 文档：http://localhost:8765/docs
融资路演大屏：http://localhost:8501
Redis：localhost:6379
```

---

## 🛑 停止服务

```powershell
# 关闭对应的命令行窗口
# 或在 Redis 窗口中按 Ctrl+C
```

---

## 🔄 重新启动项目

### 激活虚拟环境
```powershell
venv\Scripts\activate.bat
```

### 启动后端服务
```powershell
python -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 8765 --reload
```

### 启动融资路演大屏（新终端）
```powershell
streamlit run cloud_server/god_dashboard.py --server.port 8501
```

### 启动 Redis（新终端）
```powershell
redis-server
```

---

## 📦 已安装的依赖

```
核心框架：
- FastAPI 104.1
- Uvicorn 0.24.0
- Streamlit 1.28.1
- Pydantic 2.5.0

LLM 和 AI：
- OpenAI 1.3.9
- DeepSeek API 0.1.0

数据库和缓存：
- SQLAlchemy 2.0.23
- Redis 5.0.1
- AioRedis 2.0.1

视觉和 OCR：
- Pillow 10.1.0
- OpenCV 4.8.1.78
- EasyOCR 1.7.0

UI 自动化：
- UIAutomator2 3.3.6
- PyAutoGUI 0.9.53

监控和日志：
- Python JSON Logger 2.0.7
- Prometheus Client 0.19.0
- PSUtil 5.9.6

总计：65 个依赖包
```

---

## 🐛 常见问题

### Q1：脚本执行失败怎么办？
```powershell
# 检查执行策略
Get-ExecutionPolicy

# 如果是 Restricted，运行
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Q2：Redis 启动失败怎么办？
```powershell
# 检查 Redis 是否已安装
redis-cli --version

# 如果未安装，手动安装
choco install redis-64 -y

# 启动 Redis
redis-server
```

### Q3：端口被占用怎么办？
```powershell
# 查找占用端口的进程
netstat -ano | findstr :8765
netstat -ano | findstr :8501
netstat -ano | findstr :6379

# 杀死进程
taskkill /PID <PID> /F
```

### Q4：如何查看日志？
```powershell
# 后端服务日志在对应的命令行窗口中
# 融资路演大屏日志在对应的命令行窗口中
# Redis 日志在对应的命令行窗口中
```

---

## 📚 相关文档

```
完整配置脚本：complete_setup.ps1
环境检查报告：ENVIRONMENT_CHECK_REPORT.md
启动脚本：start_project.bat
环境变量示例：.env.example
依赖列表：requirements.txt
架构宪法：.cursorrules
代码检查：CODE_REVIEW_AND_INTEGRATION_CHECK.md
优化方案：COMPREHENSIVE_LOGIC_CHECK_AND_OPTIMIZATION_V8.md
```

---

## ✅ 配置检查清单

- [x] Python 3.12.7
- [x] Git 2.53.0
- [x] Node.js v24.14.0
- [x] npm 11.9.0
- [x] SQLite 3.50.4
- [x] requirements.txt
- [x] .env 配置
- [ ] 虚拟环境（运行脚本自动创建）
- [ ] 项目依赖（运行脚本自动安装）
- [ ] 审计数据库（运行脚本自动初始化）
- [ ] 死信队列数据库（运行脚本自动初始化）
- [ ] Redis（运行脚本自动安装）

---

## 🎉 现在就开始

**只需一条命令，完成所有配置：**

```powershell
.\complete_setup.ps1
```

**脚本会自动：**
1. ✅ 创建虚拟环境
2. ✅ 安装所有依赖
3. ✅ 初始化数据库
4. ✅ 安装 Redis
5. ✅ 启动所有服务
6. ✅ 打开浏览器

---

**祝你使用愉快！** 🦞
