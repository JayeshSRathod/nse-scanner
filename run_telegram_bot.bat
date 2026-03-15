@echo off
cd /d C:\Users\ratho\nse-scanner

REM Fix: Force UTF-8 so emojis don't crash
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
chcp 65001 >nul

call venv\Scripts\activate.bat

echo [%date% %time%] Starting Telegram bot monitor... >> logs\scheduler.log

REM Launch GUI monitor window (replaces blank black screen)
python nse_bot_monitor.py

echo [%date% %time%] Bot monitor closed. >> logs\scheduler.log