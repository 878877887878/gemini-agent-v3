@echo off
chcp 65001
title Gemini GUI 啟動器
cls

if not exist "venv" (
    echo ❌ 未偵測到安裝環境，請先執行 install.bat
    pause
    exit /b
)

echo 🚀 正在啟動 Gemini 視窗介面...
echo 網頁將會自動開啟，請稍候...
echo.

call venv\Scripts\activate
python gui_app.py

if %errorlevel% neq 0 (
    echo.
    echo [發生錯誤] 程式意外結束，請檢查上方錯誤訊息。
)
pause