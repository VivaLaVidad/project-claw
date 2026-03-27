@echo off
chcp 65001 > nul
title Project Claw Stack

echo.
echo ============================================================
echo  Project Claw - Unified Core Stack
echo  signaling + siri webhook
if /i "%~1"=="dashboard" echo  + dashboard
if not "%~1"=="" echo  extra service: %~1
echo ============================================================
echo.

set PYTHON=d:\桌面\Project Claw\maic_env\Scripts\python.exe
set SCRIPT=d:\桌面\Project Claw\run_stack.py

set TRANSFORMERS_OFFLINE=1
set HF_HUB_OFFLINE=1
set TOKENIZERS_PARALLELISM=false

if not exist "%PYTHON%" (
    echo [ERROR] 未找到 Python 解释器: %PYTHON%
    pause
    exit /b 1
)

if not exist "%SCRIPT%" (
    echo [ERROR] 未找到启动器: %SCRIPT%
    pause
    exit /b 1
)

echo [INFO] 启动统一服务栈...
echo [INFO] 默认启动 signaling + siri
echo [INFO] 示例: start.bat dashboard
echo [INFO] 按 Ctrl+C 停止
echo.

"%PYTHON%" "%SCRIPT%" %*

echo.
echo [INFO] 服务栈已退出
pause
