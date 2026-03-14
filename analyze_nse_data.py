#!/usr/bin/env python3
"""
analyze_nse_data.py — Analyze and manage NSE data files
========================================================
Shows storage usage and helps decide what to delete.
"""

import os
import sys
from pathlib import Path
from datetime import datetime, date
from collections import defaultdict

def get_directory_size(path):
    """Get total size of directory in MB."""
    total = 0
    try:
        for entry in os.scandir(path):
            if entry.is_file(follow_symlinks=False):
                total += entry.stat().st_size
            elif entry.is_dir(follow_symlinks=False):
                total += get_directory_size(entry.path)
    except (PermissionError, FileNotFoundError):
        pass
    return total / (1024 * 1024)  # Convert to MB

def analyze_nse_data():
    """Analyze NSE data storage."""
    nse_data_path = Path("nse_data")
    
    if not nse_data_path.exists():
        print("❌ nse_data directory not found")
        return
    
    print("\n" + "="*70)
    print("NSE DATA STORAGE ANALYSIS")
    print("="*70)
    
    # Get total size
    total_mb = get_directory_size(str(nse_data_path))
    print(f"\n📊 TOTAL STORAGE: {total_mb:.2f} MB")
    
    # Analyze by year
    print(f"\n📅 BREAKDOWN BY YEAR:")
    print("-" * 70)
    
    year_sizes = {}
    year_file_counts = defaultdict(int)
    
    for year_dir in nse_data_path.iterdir():
        if year_dir.is_dir():
            year = year_dir.name
            size_mb = get_directory_size(str(year_dir))
            year_sizes[year] = size_mb
            
            # Count files
            file_count = sum(1 for _ in year_dir.rglob("*") if _.is_file())
            year_file_counts[year] = file_count
            
            print(f"  {year}:  {size_mb:8.2f} MB  ({file_count:4d} files)")
    
    # Analyze by month within latest year
    latest_year = max(year_sizes.keys())
    latest_year_path = nse_data_path / latest_year
    
    print(f"\n📆 DETAILED BREAKDOWN FOR {latest_year}:")
    print("-" * 70)
    
    month_sizes = {}
    for month_dir in sorted(latest_year_path.iterdir()):
        if month_dir.is_dir() and month_dir.name != "_monthly":
            month = month_dir.name
            size_mb = get_directory_size(str(month_dir))
            month_sizes[month] = size_mb
            
            file_count = sum(1 for _ in month_dir.rglob("*") if _.is_file())
            print(f"  Month {month}:  {size_mb:8.2f} MB  ({file_count:4d} files)")
    
    # Recommendations
    print(f"\n💡 RECOMMENDATIONS:")
    print("-" * 70)
    
    today = date.today()
    current_year = str(today.year)
    current_month = str(today.month).zfill(2)
    
    old_years = sorted([y for y in year_sizes.keys() if y != current_year])
    
    if old_years:
        print(f"\n✅ SAFE TO DELETE (Previous years - {total_mb:.2f} MB savings):")
        for year in old_years:
            size = year_sizes[year]
            file_count = year_file_counts[year]
            print(f"  • {year}/  ({size:.2f} MB, {file_count} files)")
            print(f"    └─ Command: python cleanup_nse_data.py --delete-year {year}")
    else:
        print("\n✅ Only current year data exists (2025)")
    
    # Check old months in current year
    print(f"\n⚠️  OPTIONAL TO DELETE (Older months in {current_year}):")
    print(f"    Current month: {current_month}")
    print(f"    (Keep ~3 months of recent data for trending analysis)")
    
    old_months = sorted([m for m in month_sizes.keys() if m < current_month])
    if old_months:
        recent_keep = 3
        months_to_delete = old_months[:-recent_keep] if len(old_months) > recent_keep else []
        
        if months_to_delete:
            total_delete_mb = sum(month_sizes[m] for m in months_to_delete)
            print(f"\n    Months safe to delete: {', '.join(months_to_delete)}")
            print(f"    Potential savings: {total_delete_mb:.2f} MB")
            print(f"    └─ Command: python cleanup_nse_data.py --delete-months {','.join(months_to_delete)}")
        else:
            print(f"\n    (Keep recent {recent_keep} months or all if less than {recent_keep})")
    
    # Storage guidelines
    print(f"\n📌 STORAGE GUIDELINES:")
    print("-" * 70)
    print(f"""
  What data do you need?
  
  ✅ KEEP:
     • Current year data (for active scanning)
     • Last 3 months minimum (for trend analysis)
     • Last trading day files (for reference)
  
  ❌ SAFE TO DELETE:
     • Previous year data (2025 if now in 2026)
     • Months older than 3 months
     • Duplicate or failed downloads (marked with errors)
  
  💾 TYPICAL USAGE:
     • Last 3 months: ~50-100 MB (depending on trading days)
     • Full year: ~200-400 MB
     • Multiple years: 500+ MB
    """)
    
    # Data usage summary
    print(f"\n📈 DATA USAGE SUMMARY:")
    print("-" * 70)
    print(f"Total files in nse_data/: {sum(year_file_counts.values())}")
    print(f"Year(s) stored: {', '.join(sorted(year_sizes.keys()))}")
    print(f"Current storage: {total_mb:.2f} MB")
    print(f"Recommended minimum: 50-100 MB (last 3 months)")
    
    if total_mb > 200:
        potential_savings = total_mb - 100
        print(f"⚠️  Potential savings by cleanup: {potential_savings:.2f} MB")
    
    print("\n" + "="*70)

if __name__ == "__main__":
    analyze_nse_data()
