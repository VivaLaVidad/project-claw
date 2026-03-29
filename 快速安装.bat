@echo off
REM Project Claw 快速安装脚本 - 使用国内镜像加速
REM 用法：双击运行此文件

setlocal enabledelayedexpansion
cd /d "d:\桌面\Project Claw"

echo.
echo ╔════════════════════════════════════════════════════════════╗
echo ║     🚀 Project Claw 快速安装脚本                          ║
echo ║     使用国内镜像加速 pip 下载                             ║
echo ╚════════════════════════════════════════════════════════════╝
echo.

REM 第 1 步：创建虚拟环境
echo [1/4] 创建虚拟环境...
if exist "venv" (
    echo ✓ 虚拟环境已存在
) else (
    python -m venv venv
    if %errorlevel% equ 0 (
        echo ✓ 虚拟环境创建成功
    ) else (
        echo ✗ 虚拟环境创建失败
        pause
        exit /b 1
    )
)
echo.

REM 第 2 步：激活虚拟环境
echo [2/4] 激活虚拟环境...
call venv\Scripts\activate.bat
echo ✓ 虚拟环境已激活
echo.

REM 第 3 步：升级 pip
echo [3/4] 升级 pip...
python -m pip install --upgrade pip -i https://mirrors.aliyun.com/pypi/simple/ -q
echo ✓ pip 已升级
echo.

REM 第 4 步：安装依赖（使用国内镜像）
echo [4/4] 安装依赖（使用阿里云镜像加速）...
echo 这可能需要 2-5 分钟，请耐心等待...
echo.

pip install -r requirements.txt ^
    -i https://mirrors.aliyun.com/pypi/simple/ ^
    --trusted-host mirrors.aliyun.com ^
    --default-timeout=1000

if %errorlevel% equ 0 (
    echo.
    echo ╔════════════════════════════════════════════════════════════╗
    echo ║     ✅ 安装完成！                                         ║
    echo ╚════════════════════════════════════════════════════════════╝
    echo.
    echo 现在可以运行：启动.bat
    echo.
) else (
    echo.
    echo ✗ 安装失败，请检查网络连接
    echo.
)

pause
