@echo off
REM Project Claw 后端启动脚本

echo ========================================
echo Project Claw API Server 启动脚本
echo ========================================

REM 检查 Python 是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ 错误: 未检测到 Python
    echo 请先安装 Python 3.8+
    pause
    exit /b 1
)

echo ✓ Python 已检测到

REM 检查虚拟环境
if not exist "venv" (
    echo 📦 创建虚拟环境...
    python -m venv venv
)

REM 激活虚拟环境
call venv\Scripts\activate.bat

REM 安装依赖
echo 📥 安装依赖...
pip install -r requirements.txt

REM 启动服务器
echo 🚀 启动 API 服务器...
python -m uvicorn api_server_pro:app --reload --port 8765

pause
