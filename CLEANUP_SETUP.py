#!/usr/bin/env python3
"""
180-DAY AUTO-CLEANUP — SETUP SUMMARY
=====================================

WHAT IT DOES:
  ✅ Keeps exactly 180 days (6 months) of NSE historical data
  ✅ Automatically deletes data older than 180 days
  ✅ Runs on EVERY trading day before downloading new data
  ✅ Logs all deletions for audit trail

HOW IT WORKS:
  Timeline on March 12, 2026 (Today):
  
  KEEP (180 days back):
    ├─ 2025/10 → Keep
    ├─ 2025/11 → Keep  
    ├─ 2025/12 → Keep
    └─ 2026/01, 02, 03 → Keep (latest data)
  
  DELETE (older than 180 days):
    ├─ 2025/06 → Delete ✗
    ├─ 2025/07 → Delete ✗
    ├─ 2025/08 → Delete ✗
    └─ 2025/09 → Delete ✗

NEXT TRADING SESSION (e.g., March 13, 2026):
  • Auto-cleanup runs automatically as Step 0
  • Checks cutoff date: March 13 - 180 days = September 14, 2025
  • Data older than Sept 14 gets deleted
  • Continues with normal daily pipeline

AFTER 30 DAYS (e.g., April 12, 2026):
  • Cutoff date: April 12 - 180 days = October 14, 2025
  • Now 2025/10 becomes old enough to delete
  • System automatically removes it
  • Keeps latest 180 days rolling window

CONFIGURATION:
  File: nse_daily_runner.py
  Line: KEEP_HISTORICAL_DAYS = 180  # ← Easy to change
  
  To keep 90 days:  KEEP_HISTORICAL_DAYS = 90
  To keep 365 days: KEEP_HISTORICAL_DAYS = 365
  To keep 1 year:   KEEP_HISTORICAL_DAYS = 365

MANUAL CLEANUP OPTIONS:
"""

import os
import sys
from datetime import date, timedelta
from pathlib import Path

# Show current data status
print(__doc__)

nse_data = Path("nse_data")
if nse_data.exists():
    total_files = sum(1 for _ in nse_data.rglob("*") if _.is_file())
    
    cutoff = date.today() - timedelta(days=180)
    print(f"""
YOUR CURRENT STATUS (Date: {date.today()}):
  Total files stored: {total_files}
  Cutoff date (180 days): {cutoff}
  Will delete: Data from before {cutoff}

MANUAL COMMANDS:

1. SEE WHAT WOULD BE DELETED (dry-run, safe):
   python auto_cleanup_nse_data.py --dry-run
   
2. ACTUALLY DELETE OLD DATA:
   python auto_cleanup_nse_data.py
   
3. CHANGE RETENTION PERIOD:
   python auto_cleanup_nse_data.py --keep-days 90
   python auto_cleanup_nse_data.py --keep-days 365
   
4. VIEW CLEANUP HISTORY:
   cat logs/cleanup_history.log
   
5. RUN DAILY PIPELINE (includes auto-cleanup):
   python nse_daily_runner.py

WHAT GETS DELETED:
  ✓ Old month folders (e.g., 2025/06, 2025/07)
  ✓ All .csv files in those folders
  ✓ JSON metadata files
  
WHAT DOESN'T GET DELETED:
  ✗ Today's downloaded files
  ✗ Last 180 days of data
  ✗ Database (SQLite)
  ✗ News output files
  ✗ Config files

STORAGE ESTIMATES (with 180-day keep):
  3 months old → KEEP
  6 months old → KEEP  
  7+ months old → DELETE
  
Example:
  Oct 2025 (160 days old) → Safe
  Sep 2025 (190 days old) → Will be deleted
  
AUTOMATION IN TASK SCHEDULER:
  The cleanup runs AUTOMATICALLY at the start of:
  
  python nse_daily_runner.py
  
  No additional setup needed! It's built-in.
  
VERIFICATION:
  Check logs/cleanup_history.log for what was deleted each day
  Check logs/daily_runner.log for full pipeline including cleanup

                                                          
SAFETY NOTES:
  ✅ Dry-run always works without deleting
  ✅ Every deletion is logged in cleanup_history.log
  ✅ Cleanup fails gracefully (pipeline continues)
  ✅ Only deletes data older than configured threshold
  ✅ Easy to change KEEP_HISTORICAL_DAYS if needed

""")
else:
    print("nse_data/ folder not found")
