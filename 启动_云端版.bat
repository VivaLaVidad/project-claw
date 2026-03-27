@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================
echo   Project Claw v2.0 - 龙虾云端联网版
echo   飞书多维表格同步功能已启用
echo ========================================
echo.
python lobster_mvp.py
pause
