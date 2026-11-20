@echo off
REM 一次性配置：把模型 Key 写入当前 Windows 用户的环境变量（不写入任何项目文件）
setlocal
chcp 65001 >nul

echo ============================================
echo   配置 LLM 环境变量（写入当前用户，可随时改）
echo ============================================
echo.

set /p KEY=1) 粘贴 API Key 后回车: 
if "%KEY%"=="" (
    echo [取消] 未输入 Key。
    pause
    exit /b 1
)

set /p BASE=2) 接口地址（直接回车 = DeepSeek）: 
if "%BASE%"=="" set "BASE=https://api.deepseek.com/v1"

set /p MODEL=3) 模型名（直接回车 = deepseek-chat）: 
if "%MODEL%"=="" set "MODEL=deepseek-chat"

setx LLM_BASE_URL "%BASE%" >nul
setx LLM_API_KEY "%KEY%" >nul
setx LLM_MODEL "%MODEL%" >nul

echo.
echo [完成] 已写入用户环境变量：
echo    LLM_BASE_URL = %BASE%
echo    LLM_MODEL    = %MODEL%
echo    LLM_API_KEY  = （已设置，不回显）
echo.
echo 下一步：关闭所有已打开的命令窗口，然后双击 scripts\chat.bat
echo.
pause
