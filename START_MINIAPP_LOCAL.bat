@echo off
REM Project Claw 小程序本地调试启动脚本
REM 启动 signaling_hub 后端 + 配置本地地址

setlocal enabledelayedexpansion

cd /d "%~dp0"

echo.
echo ╔════════════════════════════════════════════════════════════╗
echo ║                                                            ║
echo ║  🦞 Project Claw MiniApp Local Dev Server                 ║
echo ║  启动本地后端 + 配置小程序地址                             ║
echo ║                                                            ║
echo ╚════════════════════════════════════════════════════════════╝
echo.

REM 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python 未安装或不在 PATH 中
    pause
    exit /b 1
)

echo ✓ Python 已检测
echo.

REM 临时修改配置为本地地址
echo 📝 配置小程序本地地址...
set CONFIG_FILE=mini_program_app\utils\config.js
set BACKUP_FILE=mini_program_app\utils\config.js.bak

if exist "%CONFIG_FILE%" (
    if not exist "%BACKUP_FILE%" (
        copy "%CONFIG_FILE%" "%BACKUP_FILE%" >nul
        echo ✓ 已备份原配置
    )
    
    REM 替换为本地地址
    powershell -Command "(Get-Content '%CONFIG_FILE%') -replace 'https://project-claw-production\.up\.railway\.app', 'http://127.0.0.1:8765' | Set-Content '%CONFIG_FILE%'"
    echo ✓ 已切换到本地地址 (http://127.0.0.1:8765)
)

echo.
echo 🚀 启动 signaling_hub 后端...
echo    地址: http://127.0.0.1:8765
echo    健康检查: http://127.0.0.1:8765/health
echo.

REM 启动后端（默认关闭账本/清结算，避免本地未配 PostgreSQL 时启动失败）
set LEDGER_ENABLED=0
set CLEARING_ENABLED=0
python -m uvicorn cloud_server.signaling_hub:app --host 127.0.0.1 --port 8765

REM 清理：恢复原配置
echo.
echo 🔄 恢复原配置...
if exist "%BACKUP_FILE%" (
    copy "%BACKUP_FILE%" "%CONFIG_FILE%" >nul
    echo ✓ 已恢复原配置
)

pause
