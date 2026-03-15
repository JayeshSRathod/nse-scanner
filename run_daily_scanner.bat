@echo off
cd /d C:\Users\ratho\nse-scanner

REM Fix: Force UTF-8 so emojis don't crash
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
chcp 65001 >nul

call venv\Scripts\activate.bat

echo [%date% %time%] Starting daily scanner... >> logs\scheduler.log

REM Launch GUI progress window (this replaces the blank black screen)
python nse_progress_window.py

echo [%date% %time%] Scanner done. >> logs\scheduler.log