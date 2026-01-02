@echo off
chcp 65001
title Gemini Console Agent
cls

if not exist "venv" (
    echo ❌ 未偵測到安裝環境，請先執行 install.bat
    pause
    exit /b
)

call venv\Scripts\activate
python agent.py

pause