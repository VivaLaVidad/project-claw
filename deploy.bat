@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM Project Claw 部署脚本（Windows 版本）

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

REM 颜色定义
set "GREEN=[92m"
set "YELLOW=[93m"
set "RED=[91m"
set "NC=[0m"

REM 打印函数
setlocal enabledelayedexpansion
for /F %%A in ('copy /Z "%~f0" nul') do set "BS=%%A"

:print_info
echo %GREEN%[INFO]%NC% %~1
exit /b

:print_warn
echo %YELLOW%[WARN]%NC% %~1
exit /b

:print_error
echo %RED%[ERROR]%NC% %~1
exit /b

REM 检查环境
:check_environment
echo %GREEN%[INFO]%NC% 检查环境...

python --version >nul 2>&1
if errorlevel 1 (
    echo %RED%[ERROR]%NC% Python 未安装
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version') do set "PYTHON_VERSION=%%i"
echo %GREEN%[INFO]%NC% %PYTHON_VERSION%
exit /b 0

REM 安装依赖
:install_dependencies
echo %GREEN%[INFO]%NC% 安装依赖...

if not exist "requirements.txt" (
    echo %RED%[ERROR]%NC% requirements.txt 不存在
    exit /b 1
)

pip install -r requirements.txt
echo %GREEN%[INFO]%NC% 依赖安装完成
exit /b 0

REM 配置环境变量
:setup_env
echo %GREEN%[INFO]%NC% 配置环境变量...

if not exist ".env" (
    if exist ".env.example" (
        copy .env.example .env
        echo %YELLOW%[WARN]%NC% 已创建 .env 文件，请编辑并填入实际值
    ) else (
        echo %RED%[ERROR]%NC% .env.example 不存在
        exit /b 1
    )
)

REM 加载环境变量
for /f "delims== tokens=1,*" %%A in (.env) do (
    if not "%%A"=="" if not "%%A:~0,1%"=="#" (
        set "%%A=%%B"
    )
)
exit /b 0

REM 本地运行
:run_local
echo %GREEN%[INFO]%NC% 本地运行 Project Claw...

call :check_environment
if errorlevel 1 exit /b 1

call :install_dependencies
if errorlevel 1 exit /b 1

call :setup_env
if errorlevel 1 exit /b 1

echo %GREEN%[INFO]%NC% 启动系统...
python lobster_with_openclaw.py
exit /b

REM Docker 构建
:build_docker
echo %GREEN%[INFO]%NC% 构建 Docker 镜像...

docker --version >nul 2>&1
if errorlevel 1 (
    echo %RED%[ERROR]%NC% Docker 未安装
    exit /b 1
)

docker build -t project-claw:latest .
echo %GREEN%[INFO]%NC% Docker 镜像构建完成
exit /b

REM Docker 运行
:run_docker
echo %GREEN%[INFO]%NC% 使用 Docker 运行 Project Claw...

docker --version >nul 2>&1
if errorlevel 1 (
    echo %RED%[ERROR]%NC% Docker 未安装
    exit /b 1
)

call :setup_env
if errorlevel 1 exit /b 1

docker run -it ^
    --name project-claw ^
    -p 8000:8000 ^
    -e DEEPSEEK_API_KEY=%DEEPSEEK_API_KEY% ^
    -e FEISHU_APP_ID=%FEISHU_APP_ID% ^
    -e FEISHU_APP_SECRET=%FEISHU_APP_SECRET% ^
    -v %cd%\logs:/app/logs ^
    project-claw:latest
exit /b

REM Docker Compose 运行
:run_docker_compose
echo %GREEN%[INFO]%NC% 使用 Docker Compose 运行 Project Claw...

docker-compose --version >nul 2>&1
if errorlevel 1 (
    echo %RED%[ERROR]%NC% Docker Compose 未安装
    exit /b 1
)

call :setup_env
if errorlevel 1 exit /b 1

docker-compose up -d
echo %GREEN%[INFO]%NC% Docker Compose 启动完成
echo %GREEN%[INFO]%NC% 查看日志: docker-compose logs -f
exit /b

REM 停止 Docker Compose
:stop_docker_compose
echo %GREEN%[INFO]%NC% 停止 Docker Compose...

docker-compose down
echo %GREEN%[INFO]%NC% Docker Compose 已停止
exit /b

REM 显示帮助
:show_help
echo.
echo Project Claw 部署脚本
echo.
echo 用法: deploy.bat [命令]
echo.
echo 命令:
echo     local           本地运行（推荐开发环境）
echo     docker-build    构建 Docker 镜像
echo     docker-run      使用 Docker 运行
echo     docker-compose  使用 Docker Compose 运行（推荐生产环境）
echo     docker-stop     停止 Docker Compose
echo     help            显示此帮助信息
echo.
echo 示例:
echo     deploy.bat local
echo     deploy.bat docker-compose
echo     deploy.bat docker-stop
echo.
exit /b

REM 主函数
if "%1"=="" (
    call :show_help
    exit /b 0
)

if /i "%1"=="local" (
    call :run_local
) else if /i "%1"=="docker-build" (
    call :build_docker
) else if /i "%1"=="docker-run" (
    call :run_docker
) else if /i "%1"=="docker-compose" (
    call :run_docker_compose
) else if /i "%1"=="docker-stop" (
    call :stop_docker_compose
) else if /i "%1"=="help" (
    call :show_help
) else (
    echo %RED%[ERROR]%NC% 未知命令: %1
    call :show_help
    exit /b 1
)

endlocal
