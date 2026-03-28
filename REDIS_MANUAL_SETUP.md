# Redis 手动安装和启动指南

## 🚀 快速启动（推荐）

### 步骤 1：运行简化配置脚本
```powershell
cd "d:\桌面\Project Claw"
.\setup_simple.ps1
```

这会自动完成：
- ✅ 创建虚拟环境
- ✅ 安装所有依赖
- ✅ 初始化数据库

### 步骤 2：手动启动 Redis

#### 方式 1：使用 Chocolatey（推荐）
```powershell
# 以管理员身份打开 PowerShell

# 安装 Chocolatey（如果未安装）
Set-ExecutionPolicy Bypass -Scope Process -Force
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))

# 安装 Redis
choco install redis-64 -y

# 启动 Redis
redis-server
```

#### 方式 2：使用 Docker（最简单）
```powershell
# 启动 Redis 容器
docker run -d -p 6379:6379 redis:latest

# 验证
redis-cli ping
# 应该返回 PONG
```

#### 方式 3：手动下载
```powershell
# 下载 Redis for Windows
# https://github.com/microsoftarchive/redis/releases

# 解压后运行
redis-server.exe
```

#### 方式 4：使用 WSL2
```powershell
# 在 WSL2 中安装 Redis
wsl sudo apt-get update
wsl sudo apt-get install redis-server -y

# 启动 Redis
wsl redis-server
```

---

## 📍 启动所有服务

### 终端 1：启动 Redis
```powershell
redis-server
```

### 终端 2：启动后端服务
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

---

## ✅ 验证所有服务

### 检查 Redis
```powershell
redis-cli ping
# 应该返回 PONG
```

### 检查后端服务
```powershell
curl http://localhost:8765/docs
# 应该返回 Swagger UI 页面
```

### 检查融资路演大屏
```powershell
curl http://localhost:8501
# 应该返回 Streamlit 页面
```

---

## 📍 服务地址

```
后端 API：http://localhost:8765
API 文档：http://localhost:8765/docs
融资路演大屏：http://localhost:8501
Redis：localhost:6379
```

---

## 🛑 停止服务

```powershell
# 在对应的终端中按 Ctrl+C
```

---

## 🐛 常见问题

### Q1：Redis 安装失败怎么办？
```powershell
# 使用 Docker 替代
docker run -d -p 6379:6379 redis:latest
```

### Q2：C 盘空间不足怎么办？
```powershell
# 检查 C 盘空间
Get-Volume C

# 清理临时文件
Remove-Item $env:TEMP\* -Recurse -Force

# 或者在 D 盘安装 Redis
# 下载 Redis for Windows 并解压到 D 盘
```

### Q3：依赖安装失败怎么办？
```powershell
# 重新运行脚本
.\setup_simple.ps1

# 或手动安装
pip install -r requirements.txt --ignore-installed
```

---

## 💡 推荐方案

**如果 C 盘空间充足：**
```powershell
# 使用 Chocolatey 安装 Redis
choco install redis-64 -y
redis-server
```

**如果 C 盘空间不足：**
```powershell
# 使用 Docker 启动 Redis
docker run -d -p 6379:6379 redis:latest
```

**如果都不想用：**
```powershell
# Redis 是可选的，项目可以在没有 Redis 的情况下运行
# 只是某些缓存功能可能不可用
```

---

**现在就试试吧！** 🚀
