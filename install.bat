@echo off
chcp 65001
cls
echo ==========================================
echo 🚀 Gemini Agent 環境自動安裝腳本
echo ==========================================

:: 1. 檢查 Python 是否安裝
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] 找不到 Python！請先去 python.org 下載並安裝 Python。
    echo 務必勾選 "Add Python to PATH"
    pause
    exit /b
)

:: 2. 建立虛擬環境 (venv)
if not exist "venv" (
    echo 📦 正在建立虛擬環境...
    python -m venv venv
) else (
    echo ✅ 虛擬環境已存在
)

:: 3. 啟動虛擬環境並安裝套件
echo ⬇️  正在安裝必要的套件 (Rich, Gradio, Gemini)...
call venv\Scripts\activate
pip install -r requirements.txt

:: 4. 檢查 .env 檔案
if not exist ".env" (
    echo GEMINI_API_KEY=你的API_KEY_貼在這裡 > .env
    echo ⚠️  已建立 .env 檔案，請記得進去填寫 API Key！
)

echo ==========================================
echo ✅ 安裝完成！
echo 請雙擊 start_gui.bat 或 start_agent.bat 開始使用
echo ==========================================
pause