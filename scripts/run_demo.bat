@echo off
REM Windows one-click launcher: double-click this file, or run it from cmd.
setlocal
chcp 65001 >nul
cd /d "%~dp0.."

if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
) else (
    set "PY=python"
)

echo === mini-agent-harness :: self-repair demo ===
echo interpreter: %PY%
echo.
"%PY%" scripts\demo_repair.py
set "CODE=%ERRORLEVEL%"
echo.
if "%CODE%"=="0" (
    echo [ok] demo finished. exit code 0
) else (
    echo [failed] exit code %CODE%, see the output above.
)
echo.
echo Press any key to close this window...
pause >nul
