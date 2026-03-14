@echo off
REM Start Telegram Polling Bot and keep it running
cd /d "%~dp0"
:loop
echo [%date% %time%] Starting NSE Telegram Polling Bot...
python nse_telegram_polling.py
echo [%date% %time%] Bot stopped. Restarting in 10 seconds...
timeout /t 10
goto loop
