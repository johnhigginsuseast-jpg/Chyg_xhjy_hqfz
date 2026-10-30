@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
"%~dp0..\market-direction-ml\.venv\Scripts\python.exe" -B -X utf8 -m realtime --source http-research --status
pause
