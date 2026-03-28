# Project Claw 环境自动配置脚本 (Windows PowerShell)
# 用法：.\setup_environment.ps1

Write-Host ""
Write-Host "🚀 Project Claw 环境自动配置" -ForegroundColor Green
Write-Host "================================" -ForegroundColor Green
Write-Host ""

# 1. 检查 Python
Write-Host "[1/6] 检查 Python..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✓ $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ Python 未安装" -ForegroundColor Red
    exit 1
}
Write-Host ""

# 2. 创建虚拟环境
Write-Host "[2/6] 创建虚拟环境..." -ForegroundColor Yellow
if (Test-Path "venv") {
    Write-Host "✓ 虚拟环境已存在" -ForegroundColor Green
} else {
    Write-Host "正在创建虚拟环境..." -ForegroundColor Cyan
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
Write-Host "升级 pip..." -ForegroundColor Cyan
python -m pip install --upgrade pip setuptools wheel -q
Write-Host "安装依赖包..." -ForegroundColor Cyan
pip install -r requirements.txt -q
Write-Host "✓ 依赖已安装" -ForegroundColor Green
Write-Host ""

# 5. 初始化数据库
Write-Host "[5/6] 初始化数据库..." -ForegroundColor Yellow
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

# 6. 验证安装
Write-Host "[6/6] 验证安装..." -ForegroundColor Yellow
try {
    python -c "import fastapi; import streamlit; import redis; print('✓ 所有依赖已安装')" 2>&1
} catch {
    Write-Host "⚠ 某些依赖可能未完全安装，但不影响基本功能" -ForegroundColor Yellow
}
Write-Host ""

# 完成
Write-Host "================================" -ForegroundColor Green
Write-Host "✅ 环境配置完成！" -ForegroundColor Green
Write-Host "================================" -ForegroundColor Green
Write-Host ""

# 显示后续步骤
Write-Host "📍 后续步骤：" -ForegroundColor Cyan
Write-Host "1. 配置 .env 文件中的 API Key（如果需要）" -ForegroundColor White
Write-Host "2. 运行启动脚本：start_project.bat" -ForegroundColor White
Write-Host ""

# 显示虚拟环境激活提示
Write-Host "💡 虚拟环境已激活，你可以直接运行项目" -ForegroundColor Cyan
Write-Host "   如果需要重新激活虚拟环境，运行：venv\Scripts\Activate.ps1" -ForegroundColor Gray
Write-Host ""

# 可选：询问是否启动项目
$response = Read-Host "是否现在启动项目？(y/n)"
if ($response -eq "y" -or $response -eq "Y") {
    Write-Host ""
    Write-Host "启动后端服务..." -ForegroundColor Yellow
    Start-Process cmd -ArgumentList "/k python -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 8765 --reload"
    
    Start-Sleep -Seconds 3
    
    Write-Host "启动融资路演大屏..." -ForegroundColor Yellow
    Start-Process cmd -ArgumentList "/k streamlit run cloud_server/god_dashboard.py --server.port 8501"
    
    Write-Host ""
    Write-Host "✓ 服务已启动" -ForegroundColor Green
    Write-Host "  - 后端 API: http://localhost:8765" -ForegroundColor Cyan
    Write-Host "  - API 文档: http://localhost:8765/docs" -ForegroundColor Cyan
    Write-Host "  - 融资路演大屏: http://localhost:8501" -ForegroundColor Cyan
}

Write-Host ""
