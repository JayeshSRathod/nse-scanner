"""
main.py — Railway Entry Point
==============================
Railway runs this file. It:
1. Reads secrets from Railway environment variables
2. Builds a config module so all other scripts work
3. Creates sample scan data if none exists
4. Starts the Telegram polling bot

Required Railway Variables:
    TELEGRAM_TOKEN   — bot token from @BotFather
    TELEGRAM_CHAT_ID — your personal Telegram chat ID
"""


import os
import sys
import json
import types
from datetime import date
from pathlib import Path

# ── Force UTF-8 ───────────────────────────────────────────────
os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['PYTHONUTF8']       = '1'

# ── Load .env if running locally ──────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("[MAIN] .env loaded (local mode)")
except ImportError:
    print("[MAIN] dotenv not available — using Railway environment variables")

# ── Read secrets from environment ─────────────────────────────
TOKEN   = os.environ.get("TELEGRAM_TOKEN",   "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

print(f"[MAIN] TELEGRAM_TOKEN   = {'SET (' + TOKEN[:15] + '...)' if TOKEN else 'NOT SET'}")
print(f"[MAIN] TELEGRAM_CHAT_ID = {CHAT_ID if CHAT_ID else 'NOT SET'}")

if not TOKEN:
    print("\n[ERROR] TELEGRAM_TOKEN is not set!")
    print("[ERROR] Go to Railway → your project → Variables → add:")
    print("[ERROR]   Name : TELEGRAM_TOKEN")
    print("[ERROR]   Value: your_bot_token_here")
    sys.exit(1)

if not CHAT_ID:
    print("\n[ERROR] TELEGRAM_CHAT_ID is not set!")
    print("[ERROR] Go to Railway → your project → Variables → add:")
    print("[ERROR]   Name : TELEGRAM_CHAT_ID")
    print("[ERROR]   Value: your_chat_id_here")
    sys.exit(1)

# ── Build config module from environment ──────────────────────
# config.py is in .gitignore so Railway never has it.
# We create it dynamically from environment variables.
config              = types.ModuleType("config")
config.TELEGRAM_TOKEN  = TOKEN
config.TELEGRAM_CHATID = CHAT_ID   # note: handler uses CHATID not CHAT_ID
config.OUTPUT_DIR      = "output"
config.LOG_DIR         = "logs"
config.DB_PATH         = "nse_scanner.db"
config.NSE_DATA_DIR    = "nse_data"
config.DATA_DIR        = "nse_data"

# Scanner thresholds (used by nse_scanner if it runs)
config.MIN_PRICE      = 50
config.MIN_VOLUME     = 50000
config.MIN_DELIVERY   = 35
config.MAX_ANNVOL     = 1.5
config.MAX_PE         = 80
config.TOP_N_STOCKS   = 25
config.WEIGHT_1M      = 0.20
config.WEIGHT_2M      = 0.30
config.WEIGHT_3M      = 0.50
config.DAYS_1M        = 22
config.DAYS_2M        = 44
config.DAYS_3M        = 66
config.BONUS_52W_HIGH = 0.05
config.BONUS_TOP25    = 0.03

# Inject into sys.modules — all imports will find it
sys.modules["config"] = config
print("[MAIN] Config module built from environment variables")

# ── Create required folders ───────────────────────────────────
for folder in ["logs", "output", "nse_data"]:
    Path(folder).mkdir(exist_ok=True)

# ── Ensure scan data exists ───────────────────────────────────
RESULTS_FILE = Path("telegram_last_scan.json")

if not RESULTS_FILE.exists():
    print("[MAIN] No telegram_last_scan.json found")
    print("[MAIN] Writing sample data so bot has something to show")

    sample = {
        "scan_date":    str(date.today()),
        "total_stocks": 5,
        "page_size":    5,
        "stocks": [
            {
                "rank": 1, "symbol": "RELIANCE", "score": 8,
                "return_1m_pct": 5.2, "return_2m_pct": 9.1,
                "return_3m_pct": 18.4, "close": 2450,
                "volume": 8500000, "delivery_pct": 52.3,
                "sl": 2278, "target1": 2622, "target2": 2794
            },
            {
                "rank": 2, "symbol": "HDFCBANK", "score": 7,
                "return_1m_pct": 4.1, "return_2m_pct": 7.8,
                "return_3m_pct": 14.2, "close": 1680,
                "volume": 12000000, "delivery_pct": 61.5,
                "sl": 1562, "target1": 1798, "target2": 1916
            },
            {
                "rank": 3, "symbol": "INFY", "score": 7,
                "return_1m_pct": 3.8, "return_2m_pct": 6.2,
                "return_3m_pct": 11.5, "close": 1520,
                "volume": 6200000, "delivery_pct": 55.8,
                "sl": 1414, "target1": 1626, "target2": 1732
            },
            {
                "rank": 4, "symbol": "TCS", "score": 6,
                "return_1m_pct": 2.9, "return_2m_pct": 5.1,
                "return_3m_pct": 9.8, "close": 3820,
                "volume": 3100000, "delivery_pct": 67.2,
                "sl": 3553, "target1": 4087, "target2": 4354
            },
            {
                "rank": 5, "symbol": "WIPRO", "score": 6,
                "return_1m_pct": 2.1, "return_2m_pct": 4.3,
                "return_3m_pct": 8.2, "close": 480,
                "volume": 9800000, "delivery_pct": 48.6,
                "sl": 446, "target1": 514, "target2": 548
            },
        ]
    }
    RESULTS_FILE.write_text(json.dumps(sample, indent=2), encoding="utf-8")
    print("[MAIN] Sample data written — send /start to see it")
    print("[MAIN] For real data: upload your telegram_last_scan.json")
else:
    try:
        data = json.loads(RESULTS_FILE.read_text(encoding="utf-8"))
        print(f"[MAIN] Scan data loaded: "
              f"{data.get('total_stocks', 0)} stocks "
              f"(date: {data.get('scan_date', '?')})")
    except Exception as e:
        print(f"[WARN] Could not read scan data: {e}")

# ── Start the polling bot ─────────────────────────────────────
print("\n[MAIN] Starting Telegram polling bot...")
print(f"[MAIN] Send 'hi' to @nsescanner_bot on Telegram\n")

try:
    # Import polling bot — config is already in sys.modules
    import nse_telegram_polling as bot
    bot.main()
except KeyboardInterrupt:
    print("\n[MAIN] Stopped by user")
except Exception as e:
    print(f"\n[MAIN] Bot crashed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
