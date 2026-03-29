@echo off
REM ═══════════════════════════════════════════════════════════════
REM Project Claw 完整一键启动脚本 v5.0
REM 功能：一键启动整个项目的所有服务
REM 用法：双击运行此文件
REM ═══════════════════════════════════════════════════════════════

setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "d:\桌面\Project Claw"

REM ═══════════════════════════════════════════════════════════════
REM 显示启动界面
REM ═══════════════════════════════════════════════════════════════

cls
echo.
echo ╔════════════════════════════════════════════════════════════╗
echo ║                                                            ║
echo ║     🚀 Project Claw 完整一键启动脚本 v5.0                ║
echo ║                                                            ║
echo ║     启动所有服务：                                        ║
echo ║     • Redis 缓存服务（端口 6379）                        ║
echo ║     • 后端 API 服务（端口 8765）                         ║
echo ║     • 融资路演大屏（端口 8501）                          ║
echo ║     • 微信小程序（微信开发者工具）                       ║
echo ║                                                            ║
echo ║     预计启动时间：2-3 分钟                               ║
echo ║                                                            ║
echo ╚════════════════════════════════════════════════════════════╝
echo.

REM ═══════════════════════════════════════════════════════════════
REM 第 1 步：环境检查
REM ═══════════════════════════════════════════════════════════════

echo [1/7] 环境检查...
echo.

REM 检查虚拟环境
if not exist "venv" (
    echo ✗ 虚拟环境不存在
    echo.
    echo 请先运行：快速安装.bat
    echo.
    pause
    exit /b 1
)
echo ✓ 虚拟环境存在

REM 检查 requirements.txt
if not exist "requirements.txt" (
    echo ✗ requirements.txt 不存在
    pause
    exit /b 1
)
echo ✓ requirements.txt 存在

REM 检查后端文件
if not exist "cloud_server\api_server_pro.py" (
    echo ✗ 后端文件不存在
    pause
    exit /b 1
)
echo ✓ 后端文件存在

REM 检查大屏文件
if not exist "cloud_server\god_dashboard.py" (
    echo ✗ 大屏文件不存在
    pause
    exit /b 1
)
echo ✓ 大屏文件存在

REM 检查小程序文件
if not exist "miniprogram\app.js" (
    echo ✗ 小程序文件不存在
    pause
    exit /b 1
)
echo ✓ 小程序文件存在

echo.

REM ═══════════════════════════════════════════════════════════════
REM 第 2 步：启动 Redis
REM ═══════════════════════════════════════════════════════════════

echo [2/7] 启动 Redis 缓存服务...
docker run -d -p 6379:6379 redis:latest >nul 2>&1
if %errorlevel% equ 0 (
    echo ✓ Redis 已启动（端口 6379）
) else (
    echo ⚠ Redis 启动失败（请确保 Docker 已安装并运行）
)
timeout /t 2 /nobreak >nul
echo.

REM ═══════════════════════════════════════════════════════════════
REM 第 3 步：启动后端 API
REM ═══════════════════════════════════════════════════════════════

echo [3/7] 启动后端 API 服务...
start "Project Claw - Backend API" cmd /k "cd /d d:\桌面\Project Claw && venv\Scripts\activate.bat && python -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 8765 --reload"
timeout /t 3 /nobreak >nul
echo ✓ 后端 API 已启动（端口 8765）
echo   访问：http://localhost:8765/docs
echo.

REM ═══════════════════════════════════════════════════════════════
REM 第 4 步：启动融资路演大屏
REM ═══════════════════════════════════════════════════════════════

echo [4/7] 启动融资路演大屏...
start "Project Claw - Dashboard" cmd /k "cd /d d:\桌面\Project Claw && venv\Scripts\activate.bat && streamlit run cloud_server/god_dashboard.py --server.port 8501"
timeout /t 3 /nobreak >nul
echo ✓ 融资路演大屏已启动（端口 8501）
echo   访问：http://localhost:8501
echo.

REM ═══════════════════════════════════════════════════════════════
REM 第 5 步：打开浏览器
REM ═══════════════════════════════════════════════════════════════

echo [5/7] 打开浏览器...
timeout /t 2 /nobreak >nul
start http://localhost:8765/docs
timeout /t 1 /nobreak >nul
start http://localhost:8501
echo ✓ 浏览器已打开
echo.

REM ═══════════════════════════════════════════════════════════════
REM 第 6 步：显示小程序启动说明
REM ═══════════════════════════════════════════════════════════════

echo [6/7] 小程序启动说明...
echo ✓ 请手动启动小程序：
echo   1. 打开微信开发者工具
echo   2. 打开项目：d:\桌面\Project Claw\miniprogram
echo   3. 点击"编译"或按 Ctrl+Shift+R
echo   4. 在模拟器中预览
echo.

REM ═══════════════════════════════════════════════════════════════
REM 第 7 步：显示启动完成信息
REM ═══════════════════════════════════════════════════════════════

echo [7/7] 启动完成！
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

echo 📊 主要功能：
echo   • C端小程序：发现商家、发起谈判、查看订单
echo   • B端大屏：实时数据、对话管理、商家管理
echo   • 后端API：Agent谈判、数据管理、统计分析
echo   • Agent系统：C端Agent与B端Agent自动谈判
echo.

echo 🛑 停止服务：
echo   • 关闭对应的命令行窗口
echo   • 或在 PowerShell 中运行：
echo     Stop-Process -Name python -Force
echo     Stop-Process -Name streamlit -Force
echo     docker stop $(docker ps -q --filter ancestor=redis:latest)
echo.

echo 📚 相关文档：
echo   • 快速启动指南：快速启动指南.md
echo   • pip 加速指南：pip加速指南.md
echo   • 详细启动步骤：DETAILED_STARTUP_STEPS.md
echo   • 完整技术总结：COMPLETE_TECHNICAL_SUMMARY.md
echo   • 深度优化方案：PROJECT_DEEP_OPTIMIZATION_V1.md
echo   • 工业级完善方案：工业级完善方案.md
echo   • 代码体检报告：代码体检报告.md
echo.

echo ═══════════════════════════════════════════════════════════════
echo 祝你使用愉快！🎉🦞
echo ═══════════════════════════════════════════════════════════════
echo.

pause
