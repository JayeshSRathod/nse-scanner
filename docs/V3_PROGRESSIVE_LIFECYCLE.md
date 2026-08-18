# NSE Scanner V3 — Progressive Signal and Compounding Lifecycle

## Frozen objective

V3 scans the eligible NSE EQ universe for stocks whose weekly performance and
relative strength are beginning to improve. Weekly structure is the discovery
and permission layer. A mechanical daily trigger and valid trade plan are
required before entry. Every entered stock starts in the 1M lifecycle and can
progress to 3M, 6M and 12M only through positive requalification.

## Selection funnel

```text
NSE universe
  -> valid completed-session data
  -> EQ, active and unrestricted
  -> price, turnover, volume and delivery
  -> market cap at least INR 1,000 crore
  -> WEEKLY_EMERGING
  -> WEEKLY_CONFIRMED
  -> daily trigger and valid 3%-8% structural risk
  -> ENTRY_PENDING
  -> ACTIVE_1M
  -> QUALIFIED_3M
  -> QUALIFIED_6M
  -> QUALIFIED_12M
  -> TRAILING or EXITED
```

Time alone never promotes a position. Promotion requires both the minimum
completed-session age and a WATCH/QUALIFIED score for the next horizon.

| Promotion | Minimum sessions | Additional requirement |
|---|---:|---|
| Entry to 3M | 20 | 3M requalification |
| 3M to 6M | 60 | 6M requalification and no failed fundamental gate |
| 6M to 12M | 120 | 12M requalification and explicit fundamental pass |

## Opportunity classifications

- `FRESH_SIGNAL`: first confirmed weekly opportunity with an actionable daily trigger.
- `NEWLY_QUALIFIED`: weekly emerging stock becomes weekly confirmed.
- `RE_ENTRY`: a previously exited opportunity develops a new actionable trigger.
- `CONTINUING`: the same opportunity remains valid.
- `WEEKLY_EMERGING`: improvement is visible but entry is not permitted.
- `UNQUALIFIED`: weekly discovery conditions are absent.

## Fail-closed controls

- Missing market-cap, turnover or delivery data prevents eligibility.
- Stale prices prevent fresh entries.
- Missing official NIFTY history prevents fresh ACTION output; WATCH research may continue.
- Regulatory restrictions prevent eligibility.
- Stop distance must remain between 3% and 8%.
- Resistance-adjusted T2 must offer at least 2R.
- Leaving the displayed ranking never closes an existing position.

## Daily reporting

1. Fresh, newly qualified and re-entry opportunities.
2. Portfolio lifecycle, progression, targets, stops and required actions.
3. Portfolio P&L, market value, realised/unrealised return and open risk.

## Operational prerequisites

Before production V3 signals are enabled:

1. Apply migrations `001_data_foundation.sql`, `002_v3_eligibility.sql` and
   `003_nse_corporate_data.sql`.
2. Populate `symbol_master_v2` with a dated market-cap file using
   `scripts/import_v3_symbol_metadata.py`.
3. Import point-in-time quarterly fundamentals with `scripts/import_v3_fundamentals.py`.
4. Populate dated regulatory restrictions.
5. Maintain at least 260 valid sessions per admitted stock and official NIFTY history.
6. Run tests, a historical walk-forward evaluation and parallel paper validation.

## NSE corporate-data policy

- Direct NSE market-cap snapshots use a 45-day live tolerance by default.
- Market cap calculated from quarterly shares outstanding and daily close is
  valid for at most 120 days.
- Annual all-company market-cap reports are classification/backfill evidence
  only; they are not accepted as live daily market cap.
- Every financial, shareholding, pledge and governance record retains its
  `available_date` (submission/broadcast date). A historical replay may select
  only records available on the simulated date.
- Banks, NBFCs and insurers require sector-specific fundamental treatment;
  ordinary debt/equity hard limits are not applied to them.
- Governance events marked `REVIEW` require admin review. Only deterministic
  events marked `SEVERE` are automatic blocks.

Use `scripts/import_nse_corporate_data.py` for normalized controlled imports.
Archive the original NSE CSV/XBRL payload before parsing so every derived row
can be reproduced and audited.

After a local shareholding bootstrap, build retained-session market caps with:

```powershell
python -m scripts.rebuild_market_caps_from_shares --db nse_scanner.db
```

The calculation uses the latest shares whose `available_date` is no later than
each price date; it never treats a later filing as historical knowledge.

## Universe and market-cap collector operations

- `scripts/run_nse_corporate_collection.py --date YYYY-MM-DD` refreshes the
  EQ security master, surveillance restrictions and available market caps,
  then exports normalized snapshots for the next disposable runner.
- Set repository variable `NSE_MARKET_CAP_URL` to the current official NSE
  all-company report download. If NSE changes or removes the URL, the collector
  retains the last valid snapshot and reports `REUSED_LAST_VALID`.
- `scripts/backfill_nse_index_history.py` downloads official daily NSE index
  snapshots for the retained 420 market sessions. The resulting
  `market_data/index_history.csv` is restored automatically on future runs.
- Quarterly shares are imported point-in-time into `shares_outstanding_v3`;
  each daily run then calculates market cap using that session's close.
- `output/nse_corporate_health.json` reports freshness, reuse and missing
  dependencies without silently converting missing data into a pass.

### Incremental shareholding operation

Step 2.6 queries NSE's official shareholding listing for the previous seven
calendar days by default (`NSE_SHAREHOLDING_WINDOW_DAYS` overrides this).  It
stores a versioned normalized filing history, so GitHub Actions downloads only
unseen filing IDs/source URLs (including new revision links), while raw XBRL
remains ignored.  A failed NSE request retains the last valid normalized data
and reports `REUSED_LAST_VALID`; routine outcomes are `FRESH`,
`NO_NEW_FILINGS`, `REUSED_LAST_VALID`, or `DEGRADED`.

The local bootstrap/fallback command is:

```powershell
python -m scripts.collect_nse_shareholding_xbrl --csv manual_import/raw/nse_shareholding_20260401_20260817.csv --as-of 2026-08-17 --limit 20
```

Use `--db nse_scanner.db` after inspecting the smoke report to import the
validated snapshot.  The CSV is a fallback only; normal Actions runs do not
require a manual download.

### 18-Aug-2026 local bootstrap and 19-Aug activation

1. Populate the normalized CSV templates in `manual_import/`.
2. Run `scripts\bootstrap_v3_18aug.ps1` from PowerShell to download official
   index history, import the files, collect the current EQ master and audit.
3. Inspect `output\v3_bootstrap_result.json`.
4. Re-run `scripts\bootstrap_v3_18aug.ps1 -Upload` only after readiness passes.
5. The production pipeline activates strict V3 from 19-Aug-2026 only when the
   operational audit passes. Otherwise it automatically runs V2-compatible
   eligibility and records the V3 blockers.
