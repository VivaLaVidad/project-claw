# Project Claw 简化环境配置脚本 (Windows PowerShell) - 稳健版
# 用法：.\setup_simple.ps1

$ErrorActionPreference = "Continue"

Write-Host ""
Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║     🚀 Project Claw 环境配置脚本 v3.0 (简化版)           ║" -ForegroundColor Cyan
Write-Host "║     包含：venv + 依赖 + 数据库                            ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# ═══════════════════════════════════════════════════════════════
# 第一步：检查 Python
# ═══════════════════════════════════════════════════════════════
Write-Host "[1/6] 检查 Python..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✓ $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ Python 未安装或不在 PATH 中" -ForegroundColor Red
    exit 1
}
Write-Host ""

# ═══════════════════════════════════════════════════════════════
# 第二步：创建虚拟环境
# ═══════════════════════════════════════════════════════════════
Write-Host "[2/6] 创建虚拟环境..." -ForegroundColor Yellow
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
Write-Host "[3/6] 激活虚拟环境..." -ForegroundColor Yellow
& "venv\Scripts\Activate.ps1"
Write-Host "✓ 虚拟环境已激活" -ForegroundColor Green
Write-Host ""

# ═══════════════════════════════════════════════════════════════
# 第四步：升级 pip 并安装依赖
# ═══════════════════════════════════════════════════════════════
Write-Host "[4/6] 安装项目依赖..." -ForegroundColor Yellow
Write-Host "升级 pip..." -ForegroundColor Cyan
python -m pip install --upgrade pip setuptools wheel -q
Write-Host "安装依赖包（这可能需要几分钟）..." -ForegroundColor Cyan
pip install -r requirements.txt -q --ignore-installed
Write-Host "✓ 依赖已安装" -ForegroundColor Green
Write-Host ""

# ═══════════════════════════════════════════════════════════════
# 第五步：初始化数据库
# ═══════════════════════════════════════════════════════════════
Write-Host "[5/6] 初始化数据库..." -ForegroundColor Yellow

# 创建临时 Python 脚本文件
$pythonScript = @"
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
"@

# 保存脚本到临时文件
$tempScript = "$env:TEMP\init_db.py"
$pythonScript | Out-File -FilePath $tempScript -Encoding UTF8

# 执行脚本
python $tempScript

if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ 数据库初始化失败" -ForegroundColor Red
    exit 1
}

# 删除临时文件
Remove-Item $tempScript -Force

Write-Host ""

# ═══════════════════════════════════════════════════════════════
# 第六步：验证安装
# ═══════════════════════════════════════════════════════════════
Write-Host "[6/6] 验证安装..." -ForegroundColor Yellow
try {
    python -c "import fastapi; import streamlit; print('✓ 核心依赖已安装')" 2>&1
} catch {
    Write-Host "⚠ 某些依赖可能未完全安装，但不影响基本功能" -ForegroundColor Yellow
}
Write-Host ""

Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║     ✅ 环境配置完成！                                     ║" -ForegroundColor Green
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""

Write-Host "📍 后续步骤：" -ForegroundColor Cyan
Write-Host "  1. 手动启动 Redis（如果已安装）：redis-server" -ForegroundColor White
Write-Host "  2. 启动后端服务：python -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 8765 --reload" -ForegroundColor White
Write-Host "  3. 启动融资路演大屏（新终端）：streamlit run cloud_server/god_dashboard.py --server.port 8501" -ForegroundColor White
Write-Host ""

Write-Host "📍 服务地址：" -ForegroundColor Cyan
Write-Host "  • 后端 API: http://localhost:8765" -ForegroundColor White
Write-Host "  • API 文档: http://localhost:8765/docs" -ForegroundColor White
Write-Host "  • 融资路演大屏: http://localhost:8501" -ForegroundColor White
Write-Host ""

Write-Host "📝 虚拟环境激活命令：" -ForegroundColor Cyan
Write-Host "  venv\Scripts\activate.bat" -ForegroundColor Gray
Write-Host ""

Write-Host "🎉 Project Claw 环境已准备就绪！" -ForegroundColor Green
Write-Host ""
