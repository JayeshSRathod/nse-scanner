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
