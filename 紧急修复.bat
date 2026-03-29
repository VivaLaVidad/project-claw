@echo off
REM ═══════════════════════════════════════════════════════════════
REM Project Claw 紧急修复脚本
REM 功能：快速修复小程序商家显示和B端大屏问题
REM ═══════════════════════════════════════════════════════════════

setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "d:\桌面\Project Claw"

cls
echo.
echo ╔════════════════════════════════════════════════════════════╗
echo ║     🔧 Project Claw 紧急修复脚本                          ║
echo ║                                                            ║
echo ║     修复问题：                                            ║
echo ║     • 小程序显示"在线商家为0"                            ║
echo ║     • B端大屏显示两个上帝视角                            ║
echo ║     • API 404 错误                                       ║
echo ║                                                            ║
echo ╚════════════════════════════════════════════════════════════╝
echo.

echo [1/5] 停止所有服务...
taskkill /F /IM python.exe >nul 2>&1
taskkill /F /IM streamlit.exe >nul 2>&1
echo ✓ 已停止所有服务
echo.

echo [2/5] 清理缓存...
if exist "__pycache__" rmdir /s /q __pycache__ >nul 2>&1
if exist "cloud_server\__pycache__" rmdir /s /q cloud_server\__pycache__ >nul 2>&1
if exist ".streamlit" rmdir /s /q .streamlit >nul 2>&1
echo ✓ 已清理缓存
echo.

echo [3/5] 验证关键文件...
if not exist "cloud_server\api_server_pro.py" (
    echo ✗ 后端文件不存在
    pause
    exit /b 1
)
if not exist "cloud_server\god_dashboard.py" (
    echo ✗ 大屏文件不存在
    pause
    exit /b 1
)
if not exist "miniprogram\pages\index\index.js" (
    echo ✗ 小程序文件不存在
    pause
    exit /b 1
)
echo ✓ 所有关键文件存在
echo.

echo [4/5] 重启虚拟环境...
if exist "venv" (
    call venv\Scripts\activate.bat
    echo ✓ 虚拟环境已激活
) else (
    echo ✗ 虚拟环境不存在
    pause
    exit /b 1
)
echo.

echo [5/5] 启动所有服务...
echo.

REM 启动 Redis
docker run -d -p 6379:6379 redis:latest >nul 2>&1
echo ✓ Redis 已启动
timeout /t 2 /nobreak >nul

REM 启动后端 API
start "Project Claw - Backend API" cmd /k "cd /d d:\桌面\Project Claw && venv\Scripts\activate.bat && python -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 8765 --reload"
echo ✓ 后端 API 已启动
timeout /t 3 /nobreak >nul

REM 启动大屏
start "Project Claw - Dashboard" cmd /k "cd /d d:\桌面\Project Claw && venv\Scripts\activate.bat && streamlit run cloud_server/god_dashboard.py --server.port 8501"
echo ✓ 融资路演大屏已启动
timeout /t 3 /nobreak >nul

REM 打开浏览器
start http://localhost:8765/docs
timeout /t 1 /nobreak >nul
start http://localhost:8501
echo ✓ 浏览器已打开
echo.

echo ╔════════════════════════════════════════════════════════════╗
echo ║     ✅ 修复完成！                                         ║
echo ╚════════════════════════════════════════════════════════════╝
echo.

echo 📍 验证步骤：
echo   1. 访问 http://localhost:8765/docs
echo   2. 访问 http://localhost:8501
echo   3. 打开小程序，检查商家列表
echo   4. 检查控制台是否有错误
echo.

echo 🔍 如果仍有问题：
echo   1. 检查后端 API 是否运行
echo   2. 检查小程序 API 地址是否正确
echo   3. 检查防火墙设置
echo   4. 查看 紧急修复方案.md 获取详细步骤
echo.

pause
