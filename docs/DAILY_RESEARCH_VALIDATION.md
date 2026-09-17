# Daily-only research validation — 17 September 2026

Implementation commit: `abe00d2c5f0ba2caab66f3a19618258d269f7c0b`.
Review: https://github.com/JayeshSRathod/nse-scanner/pull/43.

## Software verification

- Local complete regression suite: **278 passed**, one existing `utcnow()`
  deprecation warning in `scripts/audit_nse_database.py`.
- Includes 18 daily research tests: causal prefix invariance, confirmed-week and
  pivot timing, negative-return recovery eligibility, next-session fills, gap and
  same-candle stop handling, partial proceeds, costs, missing sessions, locked
  candles, corporate discontinuities, resistance room at the actual fill,
  uncertainty intervals and preserved recorded accounting.
- GitHub V2 Main Validation: successful on implementation commit, run
  https://github.com/JayeshSRathod/nse-scanner/actions/runs/35197731446.
- Production entry/exit rules and recorded portfolio state were not edited.

## Data audit

The combined SQLite and versioned daily CSV sources contain **1,031,000 rows**
and **2,993 symbols**, from 2024-12-02 through 2026-09-15. This describes source
coverage, not the number of stocks passing entry or eligibility checks.
SQLite alone ends on 2026-08-17; newer snapshots supply missing dates. The
available Nifty 500 benchmark also ends on 2026-08-17 and is not forward-filled.

Local corporate rows: market-cap snapshots 171,756; shareholding patterns 4,782;
corporate actions 184. Fundamental snapshots, promoter pledge, governance events
and P/E rows are zero. Nonzero row counts do not certify point-in-time eligibility
or corporate-action adjustment coverage.

## Preserved recorded Hull baseline

| Metric | Recorded result |
|---|---:|
| Closed trades | 60 |
| Winners / losers / breakeven | 12 / 40 / 8 |
| Win rate, including breakeven in denominator | 20.00% |
| Win-rate 95% Wilson interval | 11.83%–31.78% |
| Gross profit / gross loss | Rs 10,100.10 / Rs 21,040.87 |
| Net closed P&L, before unrecorded costs | **Rs -10,940.77** |
| Profit factor | 0.4800 |
| Average recorded closed P&L | Rs -182.35 |
| Total / average original-risk units | -5.9688R / -0.0995R |
| Hull-structure exits / trailing-stop exits | 51 / 9 |
| Same-close entries confirmed from available bars | 59 |

One recorded exit is outside that day's price range
(`PINE-20260810-3AD59BA6`); one trade has incomplete price coverage
(`PINE-20260821-40114E32`). These records are flagged, not rewritten.
Missing holding marks on 2026-08-21 and 2026-08-24 prevent a complete portfolio
drawdown claim. MFE/MAE estimates exclude entry/exit-day intrabar uncertainty.

These observations justify testing exits and execution accounting as well as
entry location. They do not establish a unique cause of the recorded losses.

## Historical experiment interpretation

Research period starts 2026-01-01; chronological holdout starts 2026-06-01 and
ends 2026-09-15. Per-side assumptions are 10 bps fees plus 5 bps slippage. Open,
review and unfilled trades remain separate from closed-trade win rates.

The four experiment arms are defined in `DAILY_RESEARCH.md`. They are **not**
replays of the deployed Hull, V3, Ladder or Penny scanners. In particular, Hull
and V3 technical cohorts are intentionally identical without invented V3
fundamentals. An apparent research improvement is not an operational promotion.

The first full-universe run completed with zero symbol-processing errors. Its
Hull/V3 mature control had 161 holdout closes, 30.43% wins, +0.03R expectancy and
1.05 profit factor. The daily-location arm had 154 closes, 20.13% wins, -0.31R
expectancy and 0.60 profit factor. This **did not support activating the proposed
entry changes**. Revised exits are evaluated independently rather than changing
the entry thresholds to fit the observed holdout.

The earlier artifacts remain under `output/daily_research_baseline/`.

## Verified final-code experiments

Both complete runs finished with **zero symbol-processing errors** and the same
source/engine fingerprints. All generated JSON was parsed and checked. Every
closed experiment trade has signal date < entry date <= exit date, nonnegative
fees and reconciled original-risk-unit P&L. All 10,268 current annotations in
each run remain operationally unqualified. The Hull audit preserves the same
60 trades and Rs -10,940.77 closed loss.

| Holdout technical experiment | Closed | Win rate | Expectancy R | Profit factor |
|---|---:|---:|---:|---:|
| Hull/V3 mature control, common exits | 161 | 30.43% | +0.0319 | 1.0482 |
| Hull/V3 progressive, common exits | 999 | 25.13% | -0.1428 | 0.7961 |
| Hull/V3 daily location, common exits | 154 | 20.13% | -0.3132 | 0.5988 |
| Ladder daily location, common exits | 156 | 20.51% | -0.3030 | 0.6113 |
| Penny daily location, common exits | 12 | 25.00% | -0.1855 | 0.7595 |
| Hull/V3 mature control, revised exits | 183 | 39.89% | +0.0441 | 1.0749 |
| Hull/V3 progressive, revised exits | 1,121 | 36.04% | -0.1030 | 0.8339 |
| Hull/V3 daily location, revised exits | 158 | 29.11% | -0.2947 | 0.6013 |
| Ladder daily location, revised exits | 160 | 28.75% | -0.3015 | 0.5928 |
| Penny daily location, revised exits | 13 | 30.77% | -0.2358 | 0.6434 |

Revised exits can change subsequent re-entry dates, trade counts and censoring;
these are independent cohort comparisons, not paired identical-trade effects.
Win-rate increases did **not** produce positive expectancy for the proposed
progressive/location cohorts. The small positive mature-control result is also
not proof of native scanner profitability or eligibility. No threshold was
retuned after observing the holdout.

Decision: **retain the implementation for offline research; do not activate the
proposed rules in deployed scanner selection or lifecycle**. Next research needs
native-strategy replay and correction/verification of recorded execution
anomalies, rather than promoting this exploratory model.

Artifacts:

- `output/daily_research_final_20260917/`: final common-exit run.
- `output/daily_research_exits_20260917/`: separate revised-exit run.
- Each contains `REPORT.md`, `comparison.json`, `manifest.json`, current
  annotations, detailed experiment trades and `hull_recorded_audit.json`.
- Price fingerprint:
  `de5ed3a0117843c2541e7825f4b1543733970cd6f49c7d5d4ace1eab13f80a52`.
- Engine fingerprint:
  `f5ca239d68ffca996d799b7e900bc30119ea2260341f9cd5efecaf5f0dc8f0ee`.
