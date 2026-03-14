# NSE Scanner — Quick Start Deployment Guide

## ✅ What's Ready

Your NSE Momentum Scanner is now complete with full Telegram pagination:

1. **Core Pipeline**: Download → Parse → Load → Scan → Output ✅
2. **Excel Reports**: Automated daily reports ✅
3. **Telegram Notifications**: Top 5 stocks + pagination for all 25 ✅
4. **Pagination System**: Browse all results with `/next`, `/prev`, `/page` ✅

## 🚀 Quick Deploy (5 minutes)

### Step 1: Install Dependencies
```bash
pip install flask requests pandas openpyxl sqlite3- python-dotenv
```

### Step 2: Verify Configuration
```bash
# Check your .env file
cat .env

# Should show:
# TELEGRAM_TOKEN=8659199776:AAF2vBF4NadqSM5t4LTv87qpP--3Jk_IgUo
# TELEGRAM_CHATID=7872191203
```

### Step 3: Generate Pagination Data
```bash
# Create test scan data for pagination
python nse_output.py --test

# Or run scanner for real data
python nse_scanner.py
```

### Step 4: Test Locally (No Internet Required)
```bash
# Test pagination formatting
python setup_telegram_webhook.py --test-local

# Should show:
# ✅ Loaded 25 scanned stocks
# Total pages: 5
# PAGE 1 (Stocks 1-5): [formatted stocks]
```

### Step 5: Set Up Webhook (For Production)

**Option A: Using Your Domain**
```bash
# Set webhook to your server
python setup_telegram_webhook.py --set-webhook https://your-domain.com/webhook

# Verify it was set
python setup_telegram_webhook.py --info
```

**Option B: Local Testing with ngrok (Free)**
```bash
# In Terminal 1: Start ngrok tunnel
ngrok http 8080

# Copy the HTTPS URL (e.g., https://abcd1234.ngrok.io)

# In Terminal 2: Set webhook
python setup_telegram_webhook.py --set-webhook https://abcd1234.ngrok.io/webhook
```

### Step 6: Start Webhook Server
```bash
# Production
python nse_telegram_webhook.py --port 8080

# With debug logging
python nse_telegram_webhook.py --port 8080 --debug
```

### Step 7: Test on Telegram

Send to **@nsescanner_bot**:
```
/start
```

You should receive:
```
📈 NSE Momentum Stocks (Showing 1-5 of 25)

#1. STOCK_A
Score: 15.2 | 1M: 8.5% | 3M: 22.1%
Close: ₹2450.50 | Vol: 2,500,000 | Deliv: 45.2%

[... 4 more stocks ...]

📄 Page 1/5
👉 Use `/next` to see next 5 stocks
```

Then send:
```
/next
```

And you'll see stocks 6-10.

## 📊 Available Commands

| Command | What It Does |
|---------|-------------|
| `/start` | Show welcome + Top 5 stocks |
| `/next` | Next 5 stocks |
| `/prev` | Previous 5 stocks |
| `/page 2` | Jump to page 2 |
| `/list` | All stocks summary |
| `/help` | Show all commands |

## 🔧 Configuration Files

### .env (Credentials)
```
TELEGRAM_TOKEN=8659199776:AAF2vBF4NadqSM5t4LTv87qpP--3Jk_IgUo
TELEGRAM_CHATID=7872191203
MIN_PRICE=50
MIN_VOLUME=50000
MIN_DELIVERY=35
WEIGHT_3M=0.50
```

### config.py (Thresholds)
```python
MIN_PRICE = 50          # Minimum stock price
MIN_VOLUME = 50000      # Minimum daily volume
MIN_DELIVERY = 35       # Minimum delivery percentage
WEIGHT_3M = 0.50        # Momentum weight (3M strongest)
```

## 📁 Project Structure

```
nse-scanner/
├── config.py                      # Central configuration
├── nse_historical_downloader.py   # NSE data download (90 days)
├── nse_parser.py                  # Parse CSV files
├── nse_loader.py                  # Load to SQLite
├── nse_scanner.py                 # Filter + score stocks
├── nse_output.py                  # Excel + Telegram
│
├── nse_telegram_handler.py        # Pagination formatter
├── nse_telegram_webhook.py        # Webhook server (NEW)
├── setup_telegram_webhook.py      # Configuration helper (NEW)
│
├── nse_scanner.db                 # SQLite database
├── telegram_last_scan.json        # Pagination data (auto-generated)
│
├── output/                        # Excel reports
├── logs/                          # Log files
├── nse_data/                      # Downloaded NSE files
└── tests/                         # Test files
```

## 🎯 Daily Automation Setup

### Option A: Windows Task Scheduler

```bat
@echo off
REM Daily NSE Scanner - 6:30 PM

cd C:\Users\ratho\nse-scanner

REM 1. Download latest data
python nse_historical_downloader.py --date %date:~-4%-%date:~-10,2%-%date:~-7,2%

REM 2. Parse and load
python nse_loader.py

REM 3. Scan and send output
python nse_scanner.py
python nse_output.py --date %date:~-4%-%date:~-10,2%-%date:~-7,2%
```

Save as `run_nse_scanner.bat`, then:
```
Task Scheduler → Create Task → Triggered at 6:30 PM → Run run_nse_scanner.bat
```

### Option B: Linux/Mac Cron

```bash
30 18 * * * cd /home/user/nse-scanner && python nse_daily_runner.py
```

Or create `nse_daily_runner.py`:
```python
#!/usr/bin/env python3
from datetime import date
import subprocess
import os

os.chdir('/home/user/nse-scanner')

# Run pipeline
subprocess.run(['python', 'nse_historical_downloader.py'])
subprocess.run(['python', 'nse_loader.py'])
subprocess.run(['python', 'nse_scanner.py'])
subprocess.run(['python', 'nse_output.py', '--date', str(date.today())])
```

## ⚠️ Troubleshooting

### Issue: "No scan results found"
**Solution**: Run the scanner first
```bash
python nse_output.py --test
```

### Issue: Telegram command not working
**Solution**: Check webhook is set
```bash
python setup_telegram_webhook.py --info

# Should show your webhook URL
```

### Issue: Bot returns "501 Not Implemented"
**Solution**: Start the Flask server
```bash
python nse_telegram_webhook.py --port 8080
```

### Issue: "Invalid token" (401 error)
**Solution**: Verify token in .env
```bash
cat .env | grep TELEGRAM_TOKEN

# Must be: 8659199776:AAF2vBF4NadqSM5t4LTv87qpP--3Jk_IgUo
```

## 📈 What You Can Do Now

✅ **Direct Usage**:
- `python nse_scanner.py` → Scan stocks for today
- `python nse_output.py` → Generate Excel + send to Telegram
- `python nse_telegram_webhook.py --port 8080` → Start pagination server

✅ **Telegram Pagination**:
- Send `/start` to @nsescanner_bot
- Navigate with `/next`, `/prev`, `/page N`
- All 25 scanned stocks available to browse

✅ **Scheduled Execution**:
- Set up daily runs (morning/evening)
- Automatic Excel report generation
- Daily Telegram notifications

✅ **Excel Reports**:
- `output/NSE_Momentum_Top25_YYYY-MM-DD.xlsx`
- Full stock metrics with formatting
- Ready for analysis/sharing

## 📖 Documentation

See detailed docs:
- [TELEGRAM_PAGINATION.md](TELEGRAM_PAGINATION.md) - Pagination system architecture
- [setup_telegram_webhook.py](setup_telegram_webhook.py) - Helper script with all commands
- Generated files: Check `logs/` directory for execution logs

## 🔐 Security Notes

⚠️ **Important**:
- Keep `.env` file private (contains bot token)
- Don't share your bot token
- Use HTTPS only for webhook (Telegram requirement)
- Chat ID is your personal identifier, don't share

## 🎉 Summary

Your NSE Scanner is ready with:
- ✅ Complete data pipeline (90 trading days)
- ✅ Advanced filtering (5-step validation)
- ✅ Momentum scoring (top 25 stocks)
- ✅ Excel reports (daily)
- ✅ Telegram notifications (with full pagination)
- ✅ Easy deployment

**Next Step**: Deploy the webhook server and start using Telegram pagination!

```bash
python nse_telegram_webhook.py --port 8080
```

Then send `/start` to @nsescanner_bot 📱

---

Questions? Check logs in `logs/` or run `python setup_telegram_webhook.py --help`
