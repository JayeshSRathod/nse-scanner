# V3 manual bootstrap inputs

Place normalized NSE extracts here before running:

`python scripts/bootstrap_v3_official_data.py --date 2026-08-18`

Required for strict 19-Aug activation: `market_cap.csv` or sufficiently complete
`shareholding.csv`, plus the automatic 420-session index backfill. Other files
enable 6M/12M qualification and historical validation without blocking early
weekly/1M/3M discovery.

Never replace submission/broadcast `available_date` with the reporting-period date.
