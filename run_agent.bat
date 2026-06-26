@echo off
chcp 65001 >nul
title IWP Ecount RPA Agent
echo ============================================================
echo   IWP Ecount RPA Agent Starting...
echo ============================================================
echo.

cd /d "%~dp0"
python ecount_agent.py

echo.
echo   Agent stopped. Press any key to close.
pause >nul
