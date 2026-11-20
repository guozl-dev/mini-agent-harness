@echo off
REM 双击启动聊天窗口：有 LLM_API_KEY 就用真模型，没有就进离线演示模式
setlocal
chcp 65001 >nul
cd /d "%~dp0.."

if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
) else (
    set "PY=python"
)

if defined LLM_API_KEY (
    echo [mode] 真模型: %LLM_MODEL%
    "%PY%" scripts\chat.py --provider env
) else (
    echo [mode] 离线演示（未检测到 LLM_API_KEY）
    echo        要接真模型：先设置 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL 环境变量
    echo.
    "%PY%" scripts\chat.py --provider fake
)

echo.
echo 聊天已结束，按任意键关闭窗口...
pause >nul
