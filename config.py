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

"""
config.py — Project Configuration
=================================
Central configuration for NSE Scanner project.

INSTRUCTION: Open your existing config.py
             Scroll to the VERY BOTTOM
             Paste everything below AFTER your existing code
             Do NOT delete anything above
"""

# ═══════════════════════════════════════════════════════════════
# ADD BELOW THIS LINE — paste after your existing DHAN_TOKEN line
# ═══════════════════════════════════════════════════════════════

# ── Category System Settings (NEW) ────────────────────────────

# How many days of scan history to keep for streak calculation
HISTORY_DAYS = 30

# Minimum consecutive days to qualify as "Strong Pick"
STRONG_PICK_MIN_DAYS = 5

# Category display order (most exciting first)
CATEGORY_ORDER = ["uptrend", "rising", "peak", "safer", "recovering"]

# "recovering" triggers when 1M return exceeds 3M return by this margin
RECOVERING_MARGIN = 0.02   # 2 percentage points

# "recovering" only fires if 3M return is below this
RECOVERING_3M_CEILING = 0.10  # 10%

# "safer" requires delivery % above this
SAFER_DELIVERY_MIN = 55.0

# "safer" requires score at least this
SAFER_SCORE_MIN = 6

# "peak" triggers when close >= this fraction of 52W high
PEAK_52W_PCT = 0.90  # 90% of 52-week high

# ── Bot Display Settings (NEW) ────────────────────────────────

# Page size for paginated stock lists
BOT_PAGE_SIZE = 5

# Telegram message character limit (leave buffer below 4096)
TELEGRAM_CHAR_LIMIT = 4000
