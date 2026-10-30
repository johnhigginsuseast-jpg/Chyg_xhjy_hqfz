@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if not exist "runtime\dde" mkdir "runtime\dde"
echo Starting DDE probe at %DATE% %TIME%>>"runtime\dde\user-probe.log"
"%~dp0..\market-direction-ml\.venv\Scripts\python.exe" -B -X utf8 -m realtime.dde --inspect-link >>"runtime\dde\user-probe.log" 2>&1
type "runtime\dde\user-probe.log"
pause
