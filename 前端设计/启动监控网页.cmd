@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
"%~dp0..\market-direction-ml\.venv\Scripts\python.exe" -B -X utf8 "%~dp0server.py" --mode live --port 8765
pause
