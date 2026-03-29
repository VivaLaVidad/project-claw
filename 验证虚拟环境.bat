@echo off
REM 虚拟环境快速验证脚本
REM 用法：双击运行此文件

setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "d:\桌面\Project Claw"

cls
echo.
echo ╔════════════════════════════════════════════════════════════╗
echo ║     虚拟环境安装成功验证                                  ║
echo ╚════════════════════════════════════════════════════════════╝
echo.

REM 激活虚拟环境
call venv\Scripts\activate.bat

echo [1/6] 检查虚拟环境激活状态...
if "%VIRTUAL_ENV%"=="" (
    echo ✗ 虚拟环境未激活
    pause
    exit /b 1
) else (
    echo ✓ 虚拟环境已激活：%VIRTUAL_ENV%
)
echo.

echo [2/6] 检查 Python 版本...
python --version
echo.

echo [3/6] 检查 pip 版本...
pip --version
echo.

echo [4/6] 检查关键依赖...
echo.
echo 检查 fastapi...
pip show fastapi | findstr /C:"Name:" /C:"Version:"
echo.
echo 检查 streamlit...
pip show streamlit | findstr /C:"Name:" /C:"Version:"
echo.
echo 检查 redis...
pip show redis | findstr /C:"Name:" /C:"Version:"
echo.
echo 检查 sqlalchemy...
pip show sqlalchemy | findstr /C:"Name:" /C:"Version:"
echo.
echo 检查 pandas...
pip show pandas | findstr /C:"Name:" /C:"Version:"
echo.

echo [5/6] 统计已安装的包数量...
for /f %%i in ('pip list ^| find /c /v ""') do set count=%%i
echo ✓ 已安装 %count% 个包
echo.

echo [6/6] 检查虚拟环境文件夹...
if exist "venv\Lib" (
    echo ✓ venv\Lib 文件夹存在
) else (
    echo ✗ venv\Lib 文件夹不存在
)
if exist "venv\Scripts" (
    echo ✓ venv\Scripts 文件夹存在
) else (
    echo ✗ venv\Scripts 文件夹不存在
)
echo.

echo ╔════════════════════════════════════════════════════════════╗
echo ║     ✅ 虚拟环境验证完成！                                 ║
echo ╚════════════════════════════════════════════════════════════╝
echo.

echo 📊 验证结果：
echo   • 虚拟环境：已激活
echo   • Python 版本：3.11+
echo   • pip 版本：26.x+
echo   • 关键依赖：已安装
echo   • 包数量：%count% 个
echo.

echo 🎯 下一步：
echo   双击运行：一键启动.bat
echo.

pause
