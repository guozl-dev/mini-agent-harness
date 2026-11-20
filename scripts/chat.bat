@echo off
REM Chat launcher: use current env vars, fall back to HKCU\Environment (setx target)
setlocal
chcp 65001 >nul
cd /d "%~dp0.."

if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
) else (
    set "PY=python"
)

if not defined LLM_API_KEY for /f "tokens=2,*" %%a in ('reg query HKCU\Environment /v LLM_API_KEY 2^>nul ^| findstr /i "LLM_API_KEY"') do set "LLM_API_KEY=%%b"
if not defined LLM_BASE_URL for /f "tokens=2,*" %%a in ('reg query HKCU\Environment /v LLM_BASE_URL 2^>nul ^| findstr /i "LLM_BASE_URL"') do set "LLM_BASE_URL=%%b"
if not defined LLM_MODEL for /f "tokens=2,*" %%a in ('reg query HKCU\Environment /v LLM_MODEL 2^>nul ^| findstr /i "LLM_MODEL"') do set "LLM_MODEL=%%b"

if defined LLM_API_KEY (
    echo [mode] live model: %LLM_MODEL%
    echo.
    "%PY%" scripts\chat.py --provider env
) else (
    echo [mode] offline demo - no LLM_API_KEY found
    echo        run scripts\setup_llm_key.bat to configure a key
    echo.
    "%PY%" scripts\chat.py --provider fake
)

echo.
echo Chat finished. Press any key to close...
pause >nul
