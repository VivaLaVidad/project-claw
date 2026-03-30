@echo off
REM Project Claw mini_program_app 一键备份脚本（防止文件丢失）

setlocal enabledelayedexpansion
cd /d "%~dp0"

set SRC=d:\桌面\Project Claw\mini_program_app
set BACKUP_ROOT=d:\桌面\Project Claw\_imported\miniapp_backups

if not exist "%SRC%" (
  echo ❌ 源目录不存在: %SRC%
  pause
  exit /b 1
)

if not exist "%BACKUP_ROOT%" mkdir "%BACKUP_ROOT%"

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set TS=%%i
set DEST=%BACKUP_ROOT%\mini_program_app_backup_%TS%

echo 📦 正在备份...
echo    源目录: %SRC%
echo    目标目录: %DEST%

xcopy "%SRC%" "%DEST%\" /E /I /H /Y >nul
if errorlevel 1 (
  echo ❌ 备份失败，请检查权限或磁盘空间
  pause
  exit /b 1
)

echo ✅ 备份完成: %DEST%
pause
