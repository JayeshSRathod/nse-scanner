# Index Data Source Policy

## Production sources

1. NSE Historical Index Data CSV for backfill and gap repair.
2. NSE/NSE Indices daily `ind_close_all_DDMMYYYY.csv` snapshot for incremental updates.
3. NSE Indices historical reports portal for sector and broad-market index backfill.

## Source hierarchy

- Official NSE/NSE Indices data is mandatory for production `index_perf`.
- Repository-generated equal-weight benchmarks may be used only for validation fallback and must be labelled synthetic.
- Unofficial market-data APIs are not permitted in the production path.

## Persistence

Each accepted row must store index name, trade date, OHLC, source file, source URL class, ingestion timestamp and quality status. Primary key: `(index_name, trade_date)`.

## Required indices

- NIFTY 50
- NIFTY 500 or NIFTY Total Market
- NIFTY BANK
- NIFTY FINANCIAL SERVICES
- NIFTY IT
- NIFTY FMCG
- NIFTY PHARMA
- NIFTY AUTO
- NIFTY METAL
- NIFTY REALTY
- NIFTY ENERGY
- NIFTY MEDIA
- NIFTY PSU BANK
- NIFTY PRIVATE BANK
- NIFTY CONSUMER DURABLES
- NIFTY HEALTHCARE INDEX
- NIFTY OIL & GAS

## Failure handling

If the official daily file is unavailable, retain the last valid index date, mark the index dataset stale, and block sector-relative scoring. Stock-only breadth may continue with a visible degraded-data flag.
