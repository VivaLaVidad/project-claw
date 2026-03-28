@echo off
REM Project Claw 一键启动脚本 v1.0 (Windows)
REM 用法：start_project.bat

setlocal enabledelayedexpansion

echo.
echo 🚀 Project Claw 启动系统
echo ================================
echo.

REM 1. 检查 Python 版本
echo [1/10] 检查 Python 版本...
python --version >nul 2>&1
if errorlevel 1 (
    echo ✗ Python 未安装或不在 PATH 中
    pause
    exit /b 1
)
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo ✓ Python 版本: %PYTHON_VERSION%
echo.

REM 2. 创建虚拟环境
echo [2/10] 创建虚拟环境...
if not exist "venv" (
    python -m venv venv
    echo ✓ 虚拟环境已创建
) else (
    echo ✓ 虚拟环境已存在
)
echo.

REM 3. 激活虚拟环境
echo [3/10] 激活虚拟环境...
call venv\Scripts\activate.bat
echo ✓ 虚拟环境已激活
echo.

REM 4. 升级 pip
echo [4/10] 升级 pip...
python -m pip install --upgrade pip setuptools wheel -q
echo ✓ pip 已升级
echo.

REM 5. 安装依赖
echo [5/10] 安装项目依赖...
if exist "requirements.txt" (
    pip install -r requirements.txt -q
    echo ✓ 依赖已安装
) else (
    echo ✗ requirements.txt 不存在
    pause
    exit /b 1
)
echo.

REM 6. 初始化数据库
echo [6/10] 初始化数据库...
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
echo.

REM 7. 检查环境变量
echo [7/10] 检查环境变量...
if exist ".env" (
    echo ✓ .env 文件已存在
) else (
    echo ⚠ .env 文件不存在，使用默认配置
)
echo.

REM 8. 启动后端服务
echo [8/10] 启动后端服务...
start "Project Claw Backend" cmd /k python -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 8765 --reload
timeout /t 3 /nobreak
echo ✓ 后端服务已启动
echo.

REM 9. 启动融资路演大屏
echo [9/10] 启动融资路演大屏...
start "Project Claw Dashboard" cmd /k streamlit run cloud_server/god_dashboard.py --server.port 8501
timeout /t 3 /nobreak
echo ✓ 融资路演大屏已启动
echo.

REM 10. 打开浏览器
echo [10/10] 打开浏览器...
start http://localhost:8765/docs
start http://localhost:8501
echo ✓ 浏览器已打开
echo.

echo ================================
echo 🎉 Project Claw 已启动！
echo ================================
echo.
echo 📍 服务地址：
echo   - 后端 API: http://localhost:8765
echo   - API 文档: http://localhost:8765/docs
echo   - 融资路演大屏: http://localhost:8501
echo   - C 端演示前端: file:///%cd%/mock_client/index.html
echo.
echo 📝 停止服务：
echo   - 关闭对应的命令行窗口
echo.
echo 📚 文档：
echo   - 架构宪法: .cursorrules
echo   - 代码检查: CODE_REVIEW_AND_INTEGRATION_CHECK.md
echo   - 优化方案: COMPREHENSIVE_LOGIC_CHECK_AND_OPTIMIZATION_V8.md
echo.

pause
