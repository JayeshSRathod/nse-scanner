#!/usr/bin/env python3
"""
Quick summary of your NSE data situation
"""
from pathlib import Path

nse_data = Path("nse_data")
print("\n📂 YOUR NSE DATA SITUATION:\n" + "="*60)

for year_dir in sorted(nse_data.iterdir()):
    if year_dir.is_dir():
        year = year_dir.name
        months = [d.name for d in year_dir.iterdir() if d.is_dir() and d.name != "_monthly"]
        month_count = len(months)
        file_count = sum(1 for _ in year_dir.rglob("*") if _.is_file())
        
        print(f"\n📅 {year}:")
        print(f"   Months: {sorted(months)}")
        print(f"   Files: {file_count}")
        
        if months:
            earliest = min(months)
            latest = max(months)
            print(f"   Range: {earliest} to {latest}")

print("\n" + "="*60)
print("\n✅ WHAT YOU CAN DO:\n")
print("1️⃣  DELETE OLD YEAR:")
print("   python cleanup_nse_data.py --delete-year 2025 --confirm")
print("   (Safe: 2025 data is old)\n")

print("2️⃣  KEEP ONLY RECENT DATA:")
print("   python cleanup_nse_data.py --keep-months 3 --confirm")
print("   (Keeps current + 3 months old)\n")

print("3️⃣  DELETE SPECIFIC MONTHS:")
print("   python cleanup_nse_data.py --delete-months 01,02 --year 2026 --confirm")
print("   (Deletes Jan/Feb from 2026)\n")

print("4️⃣  FIRST PREVIEW WHAT WILL BE DELETED (DRY RUN):")
print("   python cleanup_nse_data.py --delete-year 2025")
print("   (Shows what would be deleted, doesn't delete)\n")

print("="*60)
print("\n💡 DECISION GUIDE:\n")
print("   🔵 Keep if: You analyze historical trends (1-2 years)")
print("   🟠 Delete if: Storage is full & you only need recent data")  
print("   🟢 Safe to delete: 2025 data if you're in 2026")
print("\n" + "="*60)
