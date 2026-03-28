# Project Claw 环境检查和自动配置报告

## 📊 当前环境状态检查

### ✅ 已有的环境
```
操作系统：Windows 11 Education (x64)
Python：3.12.7 ✓
Git：2.53.0 ✓
Node.js：v24.14.0 ✓
npm：11.9.0 ✓
SQLite：3.50.4 ✓
项目文件：requirements.txt ✓
配置文件：.env ✓
配置示例：.env.example ✓
```

### ⚠️ 缺失的环境
```
虚拟环境：venv ✗ (需要创建)
审计数据库：audit.db ✗ (需要初始化)
死信队列数据库：dlq.db ✗ (需要初始化)
Redis：✗ (可选，但推荐安装)
```

---

## 🚀 自动配置步骤

### 步骤 1：创建虚拟环境
```powershell
python -m venv venv
venv\Scripts\activate.bat
```

### 步骤 2：升级 pip
```powershell
python -m pip install --upgrade pip setuptools wheel
```

### 步骤 3：安装项目依赖
```powershell
pip install -r requirements.txt
```

### 步骤 4：初始化数据库
```powershell
python << 'EOF'
import sqlite3
from pathlib import Path

# 创建审计数据库
audit_db = Path("./audit.db")
conn = sqlite3.connect(str(audit_db))
conn.execute("""
    CREATE TABLE IF NOT EXISTS audit_events (
        event_id TEXT PRIMARY KEY,
        event_type TEXT NOT NULL,
        timestamp REAL NOT NULL,
        intent_id TEXT NOT NULL,
        merchant_id TEXT NOT NULL,
        client_id TEXT NOT NULL,
        price REAL NOT NULL,
        action TEXT NOT NULL,
        details TEXT NOT NULL,
        previous_hash TEXT NOT NULL,
        event_hash TEXT NOT NULL,
        signature TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
""")
conn.commit()
conn.close()
print("✓ 审计数据库已初始化")

# 创建死信队列数据库
dlq_db = Path("./dlq.db")
conn = sqlite3.connect(str(dlq_db))
conn.execute("""
    CREATE TABLE IF NOT EXISTS dead_letters (
        id TEXT PRIMARY KEY,
        trade_id TEXT NOT NULL,
        merchant_id TEXT NOT NULL,
        client_id TEXT NOT NULL,
        amount REAL NOT NULL,
        status TEXT NOT NULL,
        payload TEXT NOT NULL,
        created_at REAL NOT NULL,
        retry_count INTEGER DEFAULT 0,
        last_error TEXT DEFAULT ''
    )
""")
conn.commit()
conn.close()
print("✓ 死信队列数据库已初始化")
EOF
```

### 步骤 5：验证安装
```powershell
python -c "import fastapi; import streamlit; import redis; print('✓ 所有依赖已安装')"
```

---

## 📦 可选：安装 Redis

### Windows 安装 Redis

#### 方式 1：使用 Chocolatey（推荐）
```powershell
# 安装 Chocolatey（如果未安装）
Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))

# 安装 Redis
choco install redis-64 -y

# 启动 Redis
redis-server
```

#### 方式 2：使用 WSL2（Windows Subsystem for Linux）
```powershell
# 在 WSL2 中安装 Redis
wsl sudo apt-get update
wsl sudo apt-get install redis-server -y

# 启动 Redis
wsl redis-server
```

#### 方式 3：使用 Docker
```powershell
# 安装 Docker Desktop（如果未安装）
# https://www.docker.com/products/docker-desktop

# 启动 Redis 容器
docker run -d -p 6379:6379 redis:latest
```

#### 方式 4：手动下载
```powershell
# 下载 Redis for Windows
# https://github.com/microsoftarchive/redis/releases

# 解压并运行
redis-server.exe
```

---

## ✅ 完整的一键配置脚本

创建文件 `setup_environment.ps1`：

```powershell
# Project Claw 环境自动配置脚本 (Windows)

Write-Host "🚀 Project Claw 环境自动配置" -ForegroundColor Green
Write-Host "================================" -ForegroundColor Green
Write-Host ""

# 1. 检查 Python
Write-Host "[1/6] 检查 Python..." -ForegroundColor Yellow
$pythonVersion = python --version 2>&1
Write-Host "✓ $pythonVersion" -ForegroundColor Green
Write-Host ""

# 2. 创建虚拟环境
Write-Host "[2/6] 创建虚拟环境..." -ForegroundColor Yellow
if (Test-Path "venv") {
    Write-Host "✓ 虚拟环境已存在" -ForegroundColor Green
} else {
    python -m venv venv
    Write-Host "✓ 虚拟环境已创建" -ForegroundColor Green
}
Write-Host ""

# 3. 激活虚拟环境
Write-Host "[3/6] 激活虚拟环境..." -ForegroundColor Yellow
& "venv\Scripts\Activate.ps1"
Write-Host "✓ 虚拟环境已激活" -ForegroundColor Green
Write-Host ""

# 4. 升级 pip 并安装依赖
Write-Host "[4/6] 安装项目依赖..." -ForegroundColor Yellow
python -m pip install --upgrade pip setuptools wheel -q
pip install -r requirements.txt -q
Write-Host "✓ 依赖已安装" -ForegroundColor Green
Write-Host ""

# 5. 初始化数据库
Write-Host "[5/6] 初始化数据库..." -ForegroundColor Yellow
python << 'PYEOF'
import sqlite3
from pathlib import Path

# 创建审计数据库
audit_db = Path("./audit.db")
if not audit_db.exists():
    conn = sqlite3.connect(str(audit_db))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            timestamp REAL NOT NULL,
            intent_id TEXT NOT NULL,
            merchant_id TEXT NOT NULL,
            client_id TEXT NOT NULL,
            price REAL NOT NULL,
            action TEXT NOT NULL,
            details TEXT NOT NULL,
            previous_hash TEXT NOT NULL,
            event_hash TEXT NOT NULL,
            signature TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()
    print("✓ 审计数据库已初始化")
else:
    print("✓ 审计数据库已存在")

# 创建死信队列数据库
dlq_db = Path("./dlq.db")
if not dlq_db.exists():
    conn = sqlite3.connect(str(dlq_db))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dead_letters (
            id TEXT PRIMARY KEY,
            trade_id TEXT NOT NULL,
            merchant_id TEXT NOT NULL,
            client_id TEXT NOT NULL,
            amount REAL NOT NULL,
            status TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at REAL NOT NULL,
            retry_count INTEGER DEFAULT 0,
            last_error TEXT DEFAULT ''
        )
    """)
    conn.commit()
    conn.close()
    print("✓ 死信队列数据库已初始化")
else:
    print("✓ 死信队列数据库已存在")
PYEOF
Write-Host ""

# 6. 验证安装
Write-Host "[6/6] 验证安装..." -ForegroundColor Yellow
python -c "import fastapi; import streamlit; print('✓ 所有依赖已安装')" 2>&1
Write-Host ""

Write-Host "================================" -ForegroundColor Green
Write-Host "✅ 环境配置完成！" -ForegroundColor Green
Write-Host "================================" -ForegroundColor Green
Write-Host ""
Write-Host "📍 后续步骤：" -ForegroundColor Cyan
Write-Host "1. 配置 .env 文件中的 API Key"
Write-Host "2. 运行启动脚本：start_project.bat"
Write-Host ""
```

运行脚本：
```powershell
# 允许执行脚本
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# 运行配置脚本
.\setup_environment.ps1
```

---

## 📋 环境配置检查清单

- [ ] Python 3.12.7 ✓
- [ ] Git 2.53.0 ✓
- [ ] Node.js v24.14.0 ✓
- [ ] npm 11.9.0 ✓
- [ ] SQLite 3.50.4 ✓
- [ ] 虚拟环境 venv（需要创建）
- [ ] 项目依赖（需要安装）
- [ ] 审计数据库 audit.db（需要初始化）
- [ ] 死信队列数据库 dlq.db（需要初始化）
- [ ] Redis（可选，推荐安装）
- [ ] .env 文件配置（已有）

---

## 🎯 推荐配置方案

### 最小配置（快速启动）
```
1. 创建虚拟环境
2. 安装依赖
3. 初始化数据库
4. 启动项目
```

### 完整配置（生产就绪）
```
1. 创建虚拟环境
2. 安装依赖
3. 初始化数据库
4. 安装 Redis
5. 配置 .env
6. 启动项目
```

---

**建议：运行 setup_environment.ps1 脚本，一键完成所有配置！** 🚀
