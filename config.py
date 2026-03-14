"""
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

# Trading days in each period (updated for 180-day analysis)
DAYS_1M        = 22        # ~1 month of trading days
DAYS_2M        = 44        # ~2 months
DAYS_3M        = 66       # ~6 months (180 trading days)

# ── Bonus Score Adjustments ───────────────────────────────────
BONUS_52W_HIGH = 0.05      # Bonus if stock near 52-week high
BONUS_TOP25    = 0.03      # Bonus if stock in top 25 by traded value

# ── API Keys (loaded from .env — never hardcode here) ─────────
TELEGRAM_TOKEN  = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHATID = os.getenv("TELEGRAM_CHAT_ID")
DHAN_CLIENT_ID  = os.getenv("DHAN_CLIENT_ID")
DHAN_TOKEN      = os.getenv("DHAN_ACCESS_TOKEN")
