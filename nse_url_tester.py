"""
nse_url_tester.py — Find Correct NSE Download URLs
=====================================================
Tests multiple URL patterns for each file to find
which ones actually work on NSE servers.

Run this ONCE — it tells you exactly which URLs work.
Results are saved to logs/url_test_results.txt

Usage:
    python nse_url_tester.py
"""

import requests
import os
from datetime import date

os.makedirs("logs", exist_ok=True)

# ── Test date — use a known trading day ──
TEST_DATE = date(2026, 3, 5)
DD        = TEST_DATE.strftime("%d")      # 05
MM        = TEST_DATE.strftime("%m")      # 03
YYYY      = TEST_DATE.strftime("%Y")      # 2026
YY        = TEST_DATE.strftime("%y")      # 26
MMM       = TEST_DATE.strftime("%b").upper()  # MAR

DDMMYYYY  = f"{DD}{MM}{YYYY}"   # 05032026
DDMMYY    = f"{DD}{MM}{YY}"     # 050326
YYYYMMDD  = TEST_DATE.strftime("%Y%m%d")  # 20260305

HEADERS = {
    "User-Agent" : "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/120.0.0.0 Safari/537.36",
    "Referer"    : "https://www.nseindia.com/",
    "Accept"     : "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# ── All URL patterns to test per file ─────────────────────────
URL_TESTS = {

    "sec_bhavdata_full (CORE)": [
        f"https://archives.nseindia.com/products/content/sec_bhavdata_full_{DDMMYYYY}.csv",
        f"https://archives.nseindia.com/content/cm/sec_bhavdata_full_{DDMMYYYY}.csv",
        f"https://www.nseindia.com/products/content/sec_bhavdata_full_{DDMMYYYY}.csv",
    ],

    "REG_IND (Blacklist)": [
        f"https://archives.nseindia.com/products/content/REG_IND{DDMMYYYY}.csv",
        f"https://archives.nseindia.com/products/content/REG_IND{DDMMYY}.csv",
        f"https://archives.nseindia.com/content/cm/REG_IND{DDMMYYYY}.csv",
        f"https://archives.nseindia.com/content/cm/REG_IND{DDMMYY}.csv",
        f"https://www1.nseindia.com/products/content/REG_IND{DDMMYYYY}.csv",
        f"https://archives.nseindia.com/products/content/REG1_IND{DDMMYYYY}.csv",
    ],

    "CMVOLT (Volatility)": [
        f"https://archives.nseindia.com/products/content/CMVOLT_{DDMMYYYY}.CSV",
        f"https://archives.nseindia.com/products/content/CMVOLT_{DDMMYYYY}.csv",
        f"https://archives.nseindia.com/content/cm/CMVOLT_{DDMMYYYY}.CSV",
        f"https://archives.nseindia.com/content/cm/CMVOLT_{DDMMYYYY}.csv",
        f"https://archives.nseindia.com/products/content/CMVOLT_{DDMMYY}.CSV",
        f"https://www1.nseindia.com/products/content/CMVOLT_{DDMMYYYY}.CSV",
    ],

    "CM_52_wk_High_low": [
        f"https://archives.nseindia.com/products/content/CM_52_wk_High_low_{DDMMYYYY}.csv",
        f"https://archives.nseindia.com/content/cm/CM_52_wk_High_low_{DDMMYYYY}.csv",
        f"https://archives.nseindia.com/products/content/cm52_wk_High_low_{DDMMYYYY}.csv",
        f"https://www1.nseindia.com/products/content/CM_52_wk_High_low_{DDMMYYYY}.csv",
        f"https://archives.nseindia.com/products/content/CM_52_wk_High_low_{DDMMYY}.csv",
    ],

    "PE Ratios": [
        f"https://archives.nseindia.com/products/content/PE_{DDMMYY}.csv",
        f"https://archives.nseindia.com/products/content/PE_{DDMMYYYY}.csv",
        f"https://archives.nseindia.com/content/cm/PE_{DDMMYY}.csv",
        f"https://archives.nseindia.com/content/cm/PE_{DDMMYYYY}.csv",
        f"https://www1.nseindia.com/products/content/PE_{DDMMYY}.csv",
    ],

    "PR Bundle ZIP": [
        f"https://archives.nseindia.com/content/cm/PR{DDMMYY}.zip",
        f"https://archives.nseindia.com/products/content/PR{DDMMYY}.zip",
        f"https://archives.nseindia.com/content/PR{DDMMYY}.zip",
        f"https://www1.nseindia.com/content/cm/PR{DDMMYY}.zip",
        f"https://archives.nseindia.com/content/cm/pr{DDMMYY}.zip",
    ],

    "MTO Delivery": [
        f"https://archives.nseindia.com/products/content/MTO_{DDMMYYYY}.DAT",
        f"https://archives.nseindia.com/content/cm/MTO_{DDMMYYYY}.DAT",
        f"https://archives.nseindia.com/products/content/MTO_{DDMMYY}.DAT",
        f"https://www1.nseindia.com/products/content/MTO_{DDMMYYYY}.DAT",
    ],

    "BhavCopy ZIP (New format)": [
        f"https://archives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{YYYYMMDD}_F_0000.csv.zip",
        f"https://archives.nseindia.com/products/content/BhavCopy_NSE_CM_0_0_0_{YYYYMMDD}_F_0000.csv.zip",
        f"https://www1.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{YYYYMMDD}_F_0000.csv.zip",
    ],

    "Short Selling": [
        f"https://archives.nseindia.com/products/content/shortselling_{DDMMYYYY}.csv",
        f"https://archives.nseindia.com/content/cm/shortselling_{DDMMYYYY}.csv",
        f"https://archives.nseindia.com/products/content/short_selling_{DDMMYYYY}.csv",
        f"https://www1.nseindia.com/products/content/shortselling_{DDMMYYYY}.csv",
    ],

    "ind_close_all (Index)": [
        f"https://archives.nseindia.com/content/indices/ind_close_all_{DDMMYYYY}.csv",
        f"https://archives.nseindia.com/products/content/ind_close_all_{DDMMYYYY}.csv",
        f"https://www1.nseindia.com/content/indices/ind_close_all_{DDMMYYYY}.csv",
    ],

    "NSE_CM_security (Monthly)": [
        f"https://archives.nseindia.com/products/content/NSE_CM_security_{DDMMYYYY}.csv.gz",
        f"https://archives.nseindia.com/content/cm/NSE_CM_security_{DDMMYYYY}.csv.gz",
        f"https://www1.nseindia.com/products/content/NSE_CM_security_{DDMMYYYY}.csv.gz",
    ],
}


def test_url(url: str) -> tuple:
    """
    Test a single URL.
    Returns (status_code, size_kb, success)
    """
    try:
        # Use HEAD first to avoid downloading large files
        r = requests.head(url, headers=HEADERS, timeout=15, allow_redirects=True)
        if r.status_code == 200:
            size = int(r.headers.get("Content-Length", 0)) / 1024
            return (200, size, True)

        # Some servers don't support HEAD — try GET with stream
        r = requests.get(url, headers=HEADERS, timeout=15, stream=True)
        if r.status_code == 200:
            # Read just first chunk to confirm it's real data
            chunk = next(r.iter_content(1024), b"")
            r.close()
            if len(chunk) > 0:
                size = int(r.headers.get("Content-Length", 0)) / 1024
                return (200, size, True)

        return (r.status_code, 0, False)

    except requests.exceptions.ConnectionError:
        return ("CONN_ERR", 0, False)
    except requests.exceptions.Timeout:
        return ("TIMEOUT", 0, False)
    except Exception as e:
        return (str(e)[:30], 0, False)


def main():
    print()
    print("=" * 65)
    print("  NSE URL Tester — Finding correct download paths")
    print(f"  Test date: {TEST_DATE.strftime('%d-%b-%Y')}")
    print("=" * 65)

    results     = {}  # file → working URL
    all_results = []  # for log file

    for file_name, urls in URL_TESTS.items():
        print(f"\n  📄 {file_name}")
        print(f"     {'─' * 55}")

        found_url = None

        for url in urls:
            status, size_kb, success = test_url(url)

            if success:
                size_str = f"{size_kb:.1f} KB" if size_kb > 0 else "size unknown"
                print(f"     [OK] {status}  {size_str}")
                print(f"        {url}")
                found_url = url
                all_results.append(f"[OK] {file_name}\n   URL: {url}\n   Status: {status}\n")
                break   # Stop at first working URL
            else:
                short_url = url.replace("https://", "").replace("archives.nseindia.com", "archives.nse")
                print(f"     [FAIL] {status}  {short_url}")
                all_results.append(f"[FAIL] {file_name} | {status} | {url}\n")

        if found_url:
            results[file_name] = found_url
        else:
            print(f"     [WARN] No working URL found for {file_name}")
            results[file_name] = None

    # ── Summary ──
    print()
    print("=" * 65)
    print("  SUMMARY")
    print("=" * 65)

    working = {k: v for k, v in results.items() if v}
    broken  = {k: v for k, v in results.items() if not v}

    print(f"\n  [OK] Working URLs : {len(working)}/{len(results)}")
    for name, url in working.items():
        print(f"     {name}")
        print(f"       -> {url}")

    if broken:
        print(f"\n  [FAIL] No URL found : {len(broken)}")
        for name in broken:
            print(f"     {name}")

    # ── Save results to log ──
    log_path = "logs/url_test_results.txt"
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"NSE URL Test Results — {TEST_DATE}\n")
        f.write("=" * 65 + "\n\n")
        f.write("\n".join(all_results))
        f.write("\n\nWORKING URLS:\n")
        for name, url in working.items():
            f.write(f"{name}:\n  {url}\n\n")

    print(f"\n  [LOG] Full results saved to: {log_path}")
    print()
    print("  -> Share the WORKING URLS section above")
    print("     and I will update nse_historical_downloader.py")
    print("=" * 65)


if __name__ == "__main__":
    main()