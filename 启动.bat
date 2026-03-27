@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================
echo   Project Claw v3.0 - 龙虾自动回复
echo ========================================
echo.
python lobster_auto_reply.py
pause
