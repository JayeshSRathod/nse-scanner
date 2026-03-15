"""
config.py — Project Configuration
=================================
Central configuration for NSE Scanner project.
"""

import os
from dotenv import load_dotenv

# Load environment variables (local development)
load_dotenv()

# ── Folder Paths ──────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

NSE_DATA_DIR = os.path.join(BASE_DIR, "nse_data")
OUTPUT_DIR   = os.path.join(BASE_DIR, "output")
LOG_DIR      = os.path.join(BASE_DIR, "logs")

DB_PATH = os.path.join(BASE_DIR, "nse_scanner.db")

# ── Scanner Filter Thresholds ─────────────────
MIN_PRICE      = 50
MIN_MARKET_CAP = 500
MIN_VOLUME     = 50000
MIN_DELIVERY   = 35
MAX_ANNVOL     = 1.5
MAX_PE         = 80
TOP_N_STOCKS   = 25

# ── Return Calculation Weights ────────────────
WEIGHT_1M = 0.20
WEIGHT_2M = 0.30
WEIGHT_3M = 0.50

# Trading days
DAYS_1M = 22
DAYS_2M = 44
DAYS_3M = 66

# ── Bonus Score Adjustments ───────────────────
BONUS_52W_HIGH = 0.05
BONUS_TOP25    = 0.03

# ── API Keys (Loaded from Environment) ────────
TELEGRAM_TOKEN  = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHATID = os.getenv("TELEGRAM_CHAT_ID")

DHAN_CLIENT_ID  = os.getenv("DHAN_CLIENT_ID")
DHAN_TOKEN      = os.getenv("DHAN_ACCESS_TOKEN")
