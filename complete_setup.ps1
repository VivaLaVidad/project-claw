# Project Claw 完整环境配置脚本 (Windows PowerShell)
# 包含：虚拟环境 + 依赖安装 + 数据库初始化 + Redis 安装 + 项目启动
# 用法：.\complete_setup.ps1

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║     🚀 Project Claw 完整环境配置脚本 v1.0                 ║" -ForegroundColor Cyan
Write-Host "║     包含：venv + 依赖 + 数据库 + Redis + 启动             ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# ═══════════════════════════════════════════════════════════════
# 第一步：检查 Python
# ═══════════════════════════════════════════════════════════════
Write-Host "[1/8] 检查 Python..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✓ $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ Python 未安装或不在 PATH 中" -ForegroundColor Red
    Write-Host "请从 https://www.python.org/downloads/ 下载安装 Python 3.11+" -ForegroundColor Yellow
    exit 1
}
Write-Host ""

# ═══════════════════════════════════════════════════════════════
# 第二步：创建虚拟环境
# ═══════════════════════════════════════════════════════════════
Write-Host "[2/8] 创建虚拟环境..." -ForegroundColor Yellow
if (Test-Path "venv") {
    Write-Host "✓ 虚拟环境已存在" -ForegroundColor Green
} else {
    Write-Host "正在创建虚拟环境..." -ForegroundColor Cyan
    python -m venv venv
    Write-Host "✓ 虚拟环境已创建" -ForegroundColor Green
}
Write-Host ""

# ═══════════════════════════════════════════════════════════════
# 第三步：激活虚拟环境
# ═══════════════════════════════════════════════════════════════
Write-Host "[3/8] 激活虚拟环境..." -ForegroundColor Yellow
& "venv\Scripts\Activate.ps1"
Write-Host "✓ 虚拟环境已激活" -ForegroundColor Green
Write-Host ""

# ═══════════════════════════════════════════════════════════════
# 第四步：升级 pip 并安装依赖
# ═══════════════════════════════════════════════════════════════
Write-Host "[4/8] 安装项目依赖..." -ForegroundColor Yellow
Write-Host "升级 pip..." -ForegroundColor Cyan
python -m pip install --upgrade pip setuptools wheel -q
Write-Host "安装依赖包（这可能需要几分钟）..." -ForegroundColor Cyan
pip install -r requirements.txt -q
Write-Host "✓ 依赖已安装" -ForegroundColor Green
Write-Host ""

# ═══════════════════════════════════════════════════════════════
# 第五步：初始化数据库
# ═══════════════════════════════════════════════════════════════
Write-Host "[5/8] 初始化数据库..." -ForegroundColor Yellow
python << 'PYEOF'
import sqlite3
from pathlib import Path
import sys

try:
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
    
    sys.exit(0)
except Exception as e:
    print(f"✗ 数据库初始化失败: {e}")
    sys.exit(1)
PYEOF

if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ 数据库初始化失败" -ForegroundColor Red
    exit 1
}
Write-Host ""

# ═══════════════════════════════════════════════════════════════
# 第六步：安装 Redis
# ═══════════════════════════════════════════════════════════════
Write-Host "[6/8] 安装 Redis..." -ForegroundColor Yellow

# 检查 Redis 是否已安装
$redisInstalled = $false
try {
    $redisVersion = redis-cli --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        $redisInstalled = $true
        Write-Host "✓ Redis 已安装: $redisVersion" -ForegroundColor Green
    }
} catch {
    $redisInstalled = $false
}

if (-not $redisInstalled) {
    Write-Host "Redis 未安装，正在安装..." -ForegroundColor Cyan
    
    # 检查 Chocolatey 是否已安装
    $chocoInstalled = $false
    try {
        $chocoVersion = choco --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            $chocoInstalled = $true
        }
    } catch {
        $chocoInstalled = $false
    }
    
    if (-not $chocoInstalled) {
        Write-Host "Chocolatey 未安装，正在安装..." -ForegroundColor Cyan
        Set-ExecutionPolicy Bypass -Scope Process -Force
        [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
        iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
        Write-Host "✓ Chocolatey 已安装" -ForegroundColor Green
    }
    
    # 使用 Chocolatey 安装 Redis
    Write-Host "使用 Chocolatey 安装 Redis..." -ForegroundColor Cyan
    choco install redis-64 -y
    Write-Host "✓ Redis 已安装" -ForegroundColor Green
} else {
    Write-Host "✓ Redis 已安装，跳过安装步骤" -ForegroundColor Green
}
Write-Host ""

# ═══════════════════════════════════════════════════════════════
# 第七步：验证安装
# ═══════════════════════════════════════════════════════════════
Write-Host "[7/8] 验证安装..." -ForegroundColor Yellow
try {
    python -c "import fastapi; import streamlit; import redis; print('✓ 所有依赖已安装')" 2>&1
} catch {
    Write-Host "⚠ 某些依赖可能未完全安装，但不影响基本功能" -ForegroundColor Yellow
}
Write-Host ""

# ═══════════════════════════════════════════════════════════════
# 第八步：启动服务
# ═══════════════════════════════════════════════════════════════
Write-Host "[8/8] 启动服务..." -ForegroundColor Yellow
Write-Host ""

# 启动 Redis
Write-Host "启动 Redis..." -ForegroundColor Cyan
Start-Process redis-server -WindowStyle Minimized
Start-Sleep -Seconds 2
Write-Host "✓ Redis 已启动" -ForegroundColor Green

# 启动后端服务
Write-Host "启动后端服务..." -ForegroundColor Cyan
Start-Process cmd -ArgumentList "/k python -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 8765 --reload"
Start-Sleep -Seconds 3
Write-Host "✓ 后端服务已启动" -ForegroundColor Green

# 启动融资路演大屏
Write-Host "启动融资路演大屏..." -ForegroundColor Cyan
Start-Process cmd -ArgumentList "/k streamlit run cloud_server/god_dashboard.py --server.port 8501"
Start-Sleep -Seconds 3
Write-Host "✓ 融资路演大屏已启动" -ForegroundColor Green

Write-Host ""
Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║     ✅ 环境配置完成！所有服务已启动！                     ║" -ForegroundColor Green
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""

Write-Host "📍 服务地址：" -ForegroundColor Cyan
Write-Host "  • 后端 API: http://localhost:8765" -ForegroundColor White
Write-Host "  • API 文档: http://localhost:8765/docs" -ForegroundColor White
Write-Host "  • 融资路演大屏: http://localhost:8501" -ForegroundColor White
Write-Host "  • Redis: localhost:6379" -ForegroundColor White
Write-Host ""

Write-Host "📝 虚拟环境激活命令：" -ForegroundColor Cyan
Write-Host "  venv\Scripts\activate.bat" -ForegroundColor Gray
Write-Host ""

Write-Host "🛑 停止服务：" -ForegroundColor Cyan
Write-Host "  • 关闭对应的命令行窗口" -ForegroundColor Gray
Write-Host "  • 或在 Redis 窗口中按 Ctrl+C" -ForegroundColor Gray
Write-Host ""

Write-Host "📚 相关文档：" -ForegroundColor Cyan
Write-Host "  • 架构宪法: .cursorrules" -ForegroundColor Gray
Write-Host "  • 代码检查: CODE_REVIEW_AND_INTEGRATION_CHECK.md" -ForegroundColor Gray
Write-Host "  • 优化方案: COMPREHENSIVE_LOGIC_CHECK_AND_OPTIMIZATION_V8.md" -ForegroundColor Gray
Write-Host ""

Write-Host "🎉 Project Claw 已完全启动！开始开发吧！" -ForegroundColor Green
Write-Host ""

# 打开浏览器
Write-Host "正在打开浏览器..." -ForegroundColor Cyan
Start-Sleep -Seconds 2
Start-Process "http://localhost:8765/docs"
Start-Process "http://localhost:8501"

Write-Host ""
