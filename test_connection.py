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
