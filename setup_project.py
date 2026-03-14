"""
NSE Scanner — Project Setup Script
====================================
Run this ONCE to create the entire project structure.
Creates all folders + files with starter template content.

Usage:
    python setup_project.py

Author  : NSE Scanner Project
Version : 1.0
"""

import os
import sys

# ─────────────────────────────────────────────────────────────
# FILE TEMPLATES — Each file gets proper starter content
# ─────────────────────────────────────────────────────────────

FILES = {

# ── config.py ──────────────────────────────────────────────
"config.py": '''"""
config.py — Project Configuration
===================================
All settings in one place.
Edit thresholds here — no need to touch scanner code.
"""

import os
from dotenv import load_dotenv

load_dotenv()  # Load secrets from .env file

# ── Folder Paths ─────────────────────────────────────────────
NSE_DATA_DIR   = "nse_data"        # Downloaded NSE files
OUTPUT_DIR     = "output"          # Excel reports
LOG_DIR        = "logs"            # Log files
DB_PATH        = "nse_scanner.db"  # SQLite database

# ── Scanner Filter Thresholds ─────────────────────────────────
MIN_PRICE      = 50        # Minimum stock price (₹) — skip penny stocks
MIN_MARKET_CAP = 500       # Minimum market cap in ₹ Crore
MIN_VOLUME     = 50000     # Minimum daily traded volume (shares)
MIN_DELIVERY   = 35        # Minimum delivery % — filters speculative trades
MAX_ANNVOL     = 1.5       # Max annualised volatility (1.5 = 150%)
MAX_PE         = 80        # P/E above this = caution flag (not excluded)
TOP_N_STOCKS   = 25        # How many stocks to show in final output

# ── Return Calculation Weights ────────────────────────────────
WEIGHT_1M      = 0.20      # 1-month return weight  (20%)
WEIGHT_2M      = 0.30      # 2-month return weight  (30%)
WEIGHT_3M      = 0.50      # 3-month return weight  (50%)

# Trading days in each period
DAYS_1M        = 22        # ~1 month of trading days
DAYS_2M        = 44        # ~2 months
DAYS_3M        = 66        # ~3 months

# ── Bonus Score Adjustments ───────────────────────────────────
BONUS_52W_HIGH = 0.05      # Bonus if stock near 52-week high
BONUS_TOP25    = 0.03      # Bonus if stock in top 25 by traded value

# ── API Keys (loaded from .env — never hardcode here) ─────────
TELEGRAM_TOKEN  = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHATID = os.getenv("TELEGRAM_CHAT_ID")
DHAN_CLIENT_ID  = os.getenv("DHAN_CLIENT_ID")
DHAN_TOKEN      = os.getenv("DHAN_ACCESS_TOKEN")
''',

# ── .env ────────────────────────────────────────────────────
".env": '''# .env — Secrets File
# =====================
# NEVER commit this file to GitHub
# Already added to .gitignore
#
# Fill in your actual values below:

TELEGRAM_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_telegram_chat_id_here
DHAN_CLIENT_ID=your_dhan_client_id_here
DHAN_ACCESS_TOKEN=your_dhan_access_token_here
''',

# ── .gitignore ───────────────────────────────────────────────
".gitignore": '''# NSE Scanner — Git Ignore Rules
# =================================

# Downloaded NSE data (too large + daily changing)
nse_data/
*.csv
*.DAT
*.gz
*.zip

# SQLite database (rebuilt locally from data)
*.db
*.sqlite
*.sqlite3
nse_scanner.db

# Excel output reports (local only)
output/
*.xlsx
*.xls

# Virtual environment (each person creates their own)
venv/
.venv/
env/
ENV/

# API Keys and Secrets (NEVER push these)
.env
*.env
config_secrets.py
credentials.py

# Python cache files
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
*.pdb

# Logs
logs/
*.log
download.log
scanner.log

# VS Code settings (optional — remove if you want to share settings)
.vscode/
*.code-workspace

# OS generated files
.DS_Store
.DS_Store?
Thumbs.db
ehthumbs.db
desktop.ini

# Pytest cache
.pytest_cache/
.coverage
htmlcov/
''',

# ── test_connection.py ───────────────────────────────────────
"test_connection.py": '''"""
test_connection.py — NSE Connection Test
==========================================
Run this first to confirm NSE archives are accessible.

Usage:
    python test_connection.py
"""

import requests
import sys

print("=" * 55)
print("  NSE Scanner — Connection Test")
print("=" * 55)

HEADERS = {
    "User-Agent" : "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/120.0.0.0 Safari/537.36",
    "Referer"    : "https://www.nseindia.com/",
    "Accept"     : "text/html,application/xhtml+xml,*/*;q=0.9",
}

# Test URLs — known working files from NSE archive
TESTS = [
    (
        "sec_bhavdata_full (Core price file)",
        "https://archives.nseindia.com/products/content/sec_bhavdata_full_05032026.csv"
    ),
    (
        "REG_IND (Blacklist file)",
        "https://archives.nseindia.com/products/content/REG_IND05032026.csv"
    ),
    (
        "CMVOLT (Volatility file)",
        "https://archives.nseindia.com/products/content/CMVOLT_05032026.CSV"
    ),
    (
        "PR Bundle ZIP (Market data)",
        "https://archives.nseindia.com/content/cm/PR050326.zip"
    ),
    (
        "ind_close_all (Index data)",
        "https://archives.nseindia.com/content/indices/ind_close_all_05032026.csv"
    ),
]

all_passed = True

for name, url in TESTS:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code == 200:
            size_kb = len(resp.content) / 1024
            print(f"  ✅ {name}")
            print(f"     Status: 200  |  Size: {size_kb:.1f} KB")

            # Show first line of CSV files
            if url.endswith(".csv") or url.endswith(".CSV"):
                first_line = resp.text.split("\\n")[0].strip()
                print(f"     Columns: {first_line[:80]}...")
        else:
            print(f"  ❌ {name}")
            print(f"     Status: {resp.status_code}")
            all_passed = False
    except Exception as e:
        print(f"  ❌ {name}")
        print(f"     Error: {e}")
        all_passed = False
    print()

print("=" * 55)
if all_passed:
    print("  ✅ ALL TESTS PASSED — NSE is accessible!")
    print("  Ready to run the historical downloader.")
else:
    print("  ⚠️  Some tests failed.")
    print("  Check your internet connection and try again.")
print("=" * 55)
''',

# ── nse_parser.py ────────────────────────────────────────────
"nse_parser.py": '''"""
nse_parser.py — NSE File Parser
==================================
Reads NSE daily CSV files and returns clean DataFrames.

Functions:
    parse_bhavdata(file_path)  → DataFrame with EQ stocks only
    parse_reg_ind(file_path)   → DataFrame with blacklisted symbols
    parse_cmvolt(file_path)    → DataFrame with volatility per stock
    parse_52wk(file_path)      → DataFrame with 52-week H/L
    parse_pe(file_path)        → DataFrame with P/E per stock
    parse_mcap(file_path)      → DataFrame with market cap per stock

Usage:
    from nse_parser import parse_bhavdata
    df = parse_bhavdata("nse_data/2026/03/05/sec_bhavdata_full_05032026.csv")
    print(df.head())

Note: All functions return None if file not found or parse fails.
"""

# ── TO BE BUILT IN NEXT SESSION ──────────────────────────────
# This file will be built step by step once connection test passes.
# Placeholder content only.

print("nse_parser.py — placeholder. Will be built in next session.")
''',

# ── nse_loader.py ────────────────────────────────────────────
"nse_loader.py": '''"""
nse_loader.py — SQLite Database Loader
========================================
Scans nse_data/ folder tree → calls parser → loads into SQLite.

Functions:
    init_database()              → Creates tables if not exist
    load_single_day(date)        → Load one day's files into DB
    load_date_range(start, end)  → Bulk load multiple days
    load_all_available()         → Load all downloaded files

Usage:
    python nse_loader.py --date 05-03-2026
    python nse_loader.py --all

Database: nse_scanner.db
    Table: daily_prices  (symbol, date, open, high, low, close, volume, delivery_pct)
    Table: blacklist     (symbol, date, flags)
    Table: volatility    (symbol, date, daily_vol, annual_vol)
"""

# ── TO BE BUILT IN NEXT SESSION ──────────────────────────────
print("nse_loader.py — placeholder. Will be built in next session.")
''',

# ── nse_scanner.py ───────────────────────────────────────────
"nse_scanner.py": '''"""
nse_scanner.py — Core Stock Scanner
======================================
Loads data from SQLite → applies filters → scores stocks →
returns ranked Top N momentum stocks.

Logic:
    1. Load last 66 days of prices from DB
    2. Apply blacklist (REG_IND flagged stocks)
    3. Apply filters: volatility, market cap, circuit breaker
    4. Calculate 1M / 2M / 3M returns per stock
    5. Apply delivery % filter (min 35%)
    6. Calculate composite score
    7. Apply bonus signals (52W high, top25 volume)
    8. Return Top 25 ranked stocks

Usage:
    python nse_scanner.py
    python nse_scanner.py --date 05-03-2026
    python nse_scanner.py --top 30
"""

# ── TO BE BUILT AFTER LOADER IS COMPLETE ─────────────────────
print("nse_scanner.py — placeholder. Will be built after loader.")
''',

# ── nse_output.py ────────────────────────────────────────────
"nse_output.py": '''"""
nse_output.py — Report Generator
===================================
Takes scanner results → generates Excel report + Telegram alert.

Functions:
    save_excel(df, date)        → Saves formatted Excel report
    send_telegram(df, date)     → Sends Top 5 to Telegram bot
    generate_report(df, date)   → Calls both above

Output Excel columns:
    Rank | Symbol | Score | 1M% | 2M% | 3M% | Close |
    Volume | DelivPct | MarketCap(Cr) | PE | 52W_Position | Flags

Usage:
    from nse_output import generate_report
    generate_report(scanner_df, date="2026-03-05")
"""

# ── TO BE BUILT AFTER SCANNER IS COMPLETE ────────────────────
print("nse_output.py — placeholder. Will be built after scanner.")
''',

# ── nse_daily_runner.py ──────────────────────────────────────
"nse_daily_runner.py": '''"""
nse_daily_runner.py — Master Automation Script
================================================
Runs the full pipeline in sequence every trading day.

Pipeline:
    6:30 PM IST → Download today\'s NSE files
    6:35 PM IST → Parse + load into SQLite
    6:40 PM IST → Run scanner
    6:45 PM IST → Generate Excel + Telegram alert

Usage:
    python nse_daily_runner.py            (runs for today)
    python nse_daily_runner.py --date 05-03-2026

Schedule (Windows Task Scheduler):
    Action  : python C:\\NSEScanner\\nse_daily_runner.py
    Trigger : Daily at 6:30 PM
    Condition: Run only when network is available
"""

# ── TO BE BUILT LAST — TIES EVERYTHING TOGETHER ──────────────
print("nse_daily_runner.py — placeholder. Built last in pipeline.")
''',

# ── README.md ────────────────────────────────────────────────
"README.md": '''# NSE Scanner 📈

**Indian Stock Market Momentum Scanner — 1 to 3 Month Returns**

Automatically downloads NSE daily data, calculates momentum scores,
and identifies top-performing stocks for short-term holding.

---

## What It Does

- Downloads daily NSE bhavcopy files automatically
- Calculates 1-month, 2-month, 3-month price returns
- Filters out regulatory-flagged stocks (ASM/GSM/IRP)
- Scores stocks by composite momentum + delivery quality
- Outputs Top 25 stocks daily as Excel report

---

## Setup

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/nse-scanner.git
cd nse-scanner

# Create virtual environment
python -m venv venv
venv\\Scripts\\activate      # Windows
source venv/bin/activate   # Mac/Linux

# Install dependencies
pip install -r requirements.txt

# Copy .env template and fill in your keys
cp .env.example .env
```

---

## First Run (Historical Bootstrap)

```bash
# Download last 90 days of data
python nse_historical_downloader.py --last 90 --quick

# Load into database
python nse_loader.py --all

# Run scanner
python nse_scanner.py
```

---

## Daily Usage

```bash
# Runs automatically via Task Scheduler at 6:30 PM IST
python nse_daily_runner.py
```

---

## Project Structure

```
NSEScanner/
├── config.py                      # All settings
├── nse_historical_downloader.py   # Download NSE files
├── nse_parser.py                  # Parse CSV files
├── nse_loader.py                  # Load into SQLite
├── nse_scanner.py                 # Core scanner logic
├── nse_output.py                  # Excel + Telegram output
├── nse_daily_runner.py            # Master automation script
├── nse_data/                      # Downloaded files (not in Git)
├── output/                        # Excel reports (not in Git)
└── nse_scanner.db                 # SQLite database (not in Git)
```

---

## Data Sources

All data from NSE India archives (no authentication needed):
- `archives.nseindia.com` — daily bhavcopy + filter files
- No paid API required for core scanner

---

## Requirements

- Python 3.11+
- See requirements.txt for libraries

---

*Built for Indian equity market momentum scanning.*
''',

}

# ─────────────────────────────────────────────────────────────
# FOLDERS TO CREATE
# ─────────────────────────────────────────────────────────────

FOLDERS = [
    "nse_data",
    "output",
    "tests",
    "logs",
]

# ─────────────────────────────────────────────────────────────
# MAIN SETUP RUNNER
# ─────────────────────────────────────────────────────────────

def main():
    print()
    print("=" * 60)
    print("   NSE Scanner — Project Setup")
    print("=" * 60)
    print()

    # Check we are in the right place
    cwd = os.getcwd()
    print(f"  📁 Creating project in: {cwd}")
    print()

    folder_count = 0
    file_count   = 0
    skip_count   = 0

    # ── Create Folders ──
    print("  Creating folders...")
    for folder in FOLDERS:
        if not os.path.exists(folder):
            os.makedirs(folder, exist_ok=True)
            print(f"    ✅ {folder}/")
            folder_count += 1
        else:
            print(f"    ⏩ {folder}/  (already exists)")
            skip_count += 1

    print()

    # ── Create Files ──
    print("  Creating files...")
    for filename, content in FILES.items():
        if not os.path.exists(filename):
            with open(filename, "w", encoding="utf-8") as f:
                f.write(content.lstrip("\n"))
            print(f"    ✅ {filename}")
            file_count += 1
        else:
            print(f"    ⏩ {filename}  (already exists — not overwritten)")
            skip_count += 1

    # ── Summary ──
    print()
    print("=" * 60)
    print(f"  ✅ Setup complete!")
    print(f"     Folders created : {folder_count}")
    print(f"     Files created   : {file_count}")
    print(f"     Already existed : {skip_count} (skipped)")
    print()
    print("  📋 Next steps:")
    print("     1. Run: python -m venv venv")
    print("     2. Run: venv\\Scripts\\activate")
    print("     3. Run: pip install requests pandas openpyxl sqlalchemy schedule python-dotenv")
    print("     4. Copy nse_historical_downloader.py into this folder")
    print("     5. Run: python test_connection.py")
    print()
    print("  📌 Reminder:")
    print("     - Fill in your .env file with Telegram + Dhan keys")
    print("     - Commit to GitHub BEFORE running the downloader")
    print("     - nse_data/ and output/ are in .gitignore — safe")
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()