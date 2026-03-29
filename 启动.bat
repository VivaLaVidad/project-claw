@echo off
REM Project Claw 一键启动脚本 - Windows Batch 版本
REM 用法：双击运行此文件即可启动所有服务

setlocal enabledelayedexpansion
cd /d "d:\桌面\Project Claw"

echo.
echo ╔════════════════════════════════════════════════════════════╗
echo ║     🚀 Project Claw 一键启动脚本                          ║
echo ║     启动所有服务：后端 + 大屏 + Redis + 小程序            ║
echo ╚════════════════════════════════════════════════════════════╝
echo.

REM 检查虚拟环境
if not exist "venv" (
    echo ✗ 虚拟环境不存在
    echo 请先运行：python -m venv venv
    pause
    exit /b 1
)

echo ✓ 虚拟环境存在
echo.

REM 启动 Redis
echo [1/4] 启动 Redis...
docker run -d -p 6379:6379 redis:latest >nul 2>&1
if %errorlevel% equ 0 (
    echo ✓ Redis 已启动（端口 6379）
) else (
    echo ⚠ Redis 启动失败（请确保 Docker 已安装）
)
echo.

REM 启动后端 API
echo [2/4] 启动后端 API...
start "Project Claw - Backend API" cmd /k "cd /d d:\桌面\Project Claw && venv\Scripts\activate.bat && python -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 8765 --reload"
timeout /t 3 /nobreak
echo ✓ 后端 API 已启动（端口 8765）
echo   访问：http://localhost:8765/docs
echo.

REM 启动融资路演大屏
echo [3/4] 启动融资路演大屏...
start "Project Claw - Dashboard" cmd /k "cd /d d:\桌面\Project Claw && venv\Scripts\activate.bat && streamlit run cloud_server/god_dashboard.py --server.port 8501"
timeout /t 3 /nobreak
echo ✓ 融资路演大屏已启动（端口 8501）
echo   访问：http://localhost:8501
echo.

REM 启动小程序提示
echo [4/4] 小程序启动说明...
echo ✓ 请手动启动小程序：
echo   1. 打开微信开发者工具
echo   2. 打开项目：d:\桌面\Project Claw\miniprogram
echo   3. 点击"编译"或按 Ctrl+Shift+R
echo   4. 在模拟器中预览
echo.

echo ╔════════════════════════════════════════════════════════════╗
echo ║     ✅ 所有服务已启动！                                   ║
echo ╚════════════════════════════════════════════════════════════╝
echo.
echo 📍 访问地址：
echo   • 后端 API 文档：http://localhost:8765/docs
echo   • 融资路演大屏：http://localhost:8501
echo   • Redis：localhost:6379
echo   • 小程序：微信开发者工具模拟器
echo.
echo 🛑 停止服务：关闭对应的命令行窗口
echo.
pause
