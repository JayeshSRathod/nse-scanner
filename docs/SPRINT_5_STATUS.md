# Sprint 5 Status — Production Orchestration

## Completed

- End-to-end V2 daily orchestrator.
- Price and official-index freshness assessment.
- Equal-weight universe fallback when official benchmark history is unavailable.
- Stale-price hard block for new candidate creation.
- Persistent-position lifecycle processing continues in degraded index mode.
- Candidate creation without duplicate active `(symbol, horizon)` positions.
- Message 1 candidate preview and Message 2 position update.
- Telegram delivery adapter with explicit opt-in and fail-closed credentials.
- Local/scheduled runner entrypoint.
- Integration tests and isolated CI workflow.

## Daily command

Dry run:

```bash
python scripts/run_v2_daily.py --db nse_scanner.db
```

Restore repository price snapshots before running:

```bash
python scripts/run_v2_daily.py --db nse_scanner.db --restore-snapshots
```

Enable Telegram only after configuring credentials:

```bash
python scripts/run_v2_daily.py --db nse_scanner.db --send-telegram
```

Preferred environment variables:

- `V2_TELEGRAM_TOKEN`
- `V2_TELEGRAM_CHAT_ID`

Legacy names remain readable for migration compatibility, but no credentials are stored in the repository.

## Outputs

- `output/v2_daily/daily_run.json`
- `output/v2_daily/message_1_candidates.txt`
- `output/v2_daily/message_2_positions.txt`

## Freshness rules

- Price history older than four calendar days blocks new candidates.
- Missing or stale official index history is displayed as a data warning.
- When official NIFTY history is unavailable, regime calculation uses a clearly labelled equal-weight NSE-universe fallback.
- Existing persistent positions continue to receive lifecycle updates when current stock OHLC data is available.

## Scheduler deployment

The recommended production deployment for Sprint 5 is the existing local machine scheduler because `nse_scanner.db` contains persistent trade state. Example Windows Task Scheduler action:

```text
Program: C:\Users\ratho\COA_Dashboard\venv\Scripts\python.exe
Arguments: scripts\run_v2_daily.py --db nse_scanner.db --send-telegram
Start in: <local nse-scanner repository path>
```

Run after the completed NSE daily-data load, not before market close.

GitHub Actions remains CI/dry-run only at this stage. Hosted runners are disposable; using them for live lifecycle processing without durable portfolio-state restoration would lose trade memory between runs.

## Next phase

Sprint 6 should add official `index_perf` ingestion, normalized index snapshots, durable state backup/restore, operational audit logs, retry controls, and deployment health reporting.
