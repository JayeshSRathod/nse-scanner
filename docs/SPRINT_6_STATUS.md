# Sprint 6 Status — Index Data and Operational Resilience

## Implemented

- Official NSE Daily Snapshot ingestion using `ind_close_all_DDMMYYYY.csv`.
- Flexible column normalization with strict required-field and trade-date validation.
- Retry/backoff network retrieval with an overridable URL template.
- Idempotent UPSERT into `index_perf` keyed by `(index_name, date)`.
- Raw official snapshot retention under `market_data/index_snapshots/`.
- SQLite online backup using the native backup API.
- SHA-256 manifest, table counts and SQLite integrity validation.
- Safe restore with optional pre-restore copy of the current database.
- Health report covering database integrity, price/index freshness and active-state counts.
- Unified operator CLI and isolated CI tests.

## Operator commands

```bash
python scripts/v2_operations.py --db nse_scanner.db index-update --date 2026-07-29
python scripts/v2_operations.py --db nse_scanner.db backup
python scripts/v2_operations.py --db nse_scanner.db health --as-of 2026-07-29
python scripts/v2_operations.py --db nse_scanner.db restore --backup backups/v2/v2_state_YYYYMMDDTHHMMSSZ.db --sha256 <checksum>
```

An already-downloaded official CSV can be loaded without a network call:

```bash
python scripts/v2_operations.py --db nse_scanner.db index-update \
  --date 2026-07-29 --csv ind_close_all_29072026.csv
```

## Recommended daily order

1. Complete stock-market data load.
2. Run official index snapshot update.
3. Run health check.
4. Create state backup.
5. Run `scripts/run_v2_daily.py`.
6. Retain logs and output messages.

## Failure policy

- Invalid, empty or date-mismatched index CSVs are rejected.
- Failed index retrieval does not overwrite prior valid rows.
- Duplicate ingestion is safe because writes are idempotent.
- Backup restore verifies integrity and optional checksum before replacement.
- Health exit codes are `0=HEALTHY`, `2=DEGRADED`, `3=CRITICAL`.

## Execution status

The implementation and CI definitions are committed. Actual GitHub Actions execution and live NSE network retrieval must be verified from the repository Actions page or the local deployment environment.
