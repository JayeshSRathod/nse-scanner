# Daily-only progressive scanner research

Implementation of the daily-data-supported recommendations in the two user
attachments. This is an isolated research path, not activation of revised
production entry rules. V8 and TradingView v17.12 are not dependencies.

## Run

From the repository root:

```powershell
python -m scripts.run_daily_research --output output/daily_research_run1
python -m scripts.run_daily_research --revised-exits --output output/daily_research_exits1
python -m pytest -q tests/test_daily_research.py
```

SQLite is opened read-only. Versioned daily CSV snapshots supply dates missing
from SQLite. Existing output directories with contents are rejected. Output is
restricted to a dedicated directory under `output/`. No Telegram, production
state, database migrations, broker API or workflow dispatch is involved.

Optional `--symbols` is for smoke tests only, not evidence of universe-wide
performance. Fee and slippage assumptions are configurable with `--fee-bps` and
`--slippage-bps` (defaults 10 and 5 basis points per side). They are research
assumptions, not verified brokerage/tax schedules.

## Implemented specification

| Attachment proposal | Implementation / boundary |
|---|---|
| Investigate Hull losses; preserve baseline | Recorded rupee and R statistics, exit reasons, T1/T2 counts, holding periods, same-close-entry diagnostics and out-of-range exit checks. Never rewrites original fills. |
| MFE, MAE and giveback | Partial daily-bar estimates excluding uncertain entry/exit-bar extrema, explicitly labelled. |
| Maximum drawdown | Recorded Hull daily NAV only when every concurrent holding has a mark; otherwise unavailable. Synthetic independent trades do not claim a portfolio drawdown. |
| Turnover instead of universal share volume | Complete median 20-session turnover, initial research floor Rs 1 crore; recent five-session deterioration warning. |
| Delivery as normal-stock quality evidence | Five/20-session delivery and own 60-session percentile; missing remains unknown. Penny retains strict ready-tier delivery thresholds. |
| P/E no longer an absolute veto | Not used by this research selector. Actual local P/E table coverage audited; no sector valuation fabricated. Native production P/E rules unchanged. |
| Progressive EMA and momentum | Recovery/developing/confirmed/pullback/range/deteriorating states, 5/10/22/44/66 returns, non-overlapping five-session acceleration, EMA50/200 maturity bonus. |
| Setup-specific volume | Breakout expansion, quiet retest/pullback, moderate recovery participation. |
| Daily support/retest zones | Confirmed swing support, prior breakout levels, EMA/Hull proximity, upper-candle close, structural invalidation and ATR-buffer stop. No order-flow, POC or intraday zone claims. |
| Qualified entry location | ATR extension and large-candle checks, stop-risk bounds, measured resistance room >=1.5R. Unknown resistance does not silently pass. |
| HTF permission | Completed weekly EMA/structure only; weekly Hybrid Hull availability shown separately. No substitution claimed to match its unavailable long warm-up. No five-timeframe agreement gate. |
| Daily execution alternative | Signal after close, trigger on a later session, five-session expiry, gap/entry-price cap and actual-fill risk checks. No LTF alert or TradingView routing. |
| Revised holding lifecycle | Separate `--revised-exits` experiment: T1 partial, next-session breakeven/confirmed structure trail, next-open deterioration exit, cooldown. No exit solely for temporary range state. This does not redefine the frozen deployed Hull trail. |
| Four scanner views | Hull/V3/common technical profiles, early-developing allowance for Ladder, strict Penny price/history/delivery/recent-turnover overlays. All remain research annotations; production eligibility and native strategy parity are not asserted. |

## Comparison contract

Four incrementally defined **new technical experiments**:

1. `mature_control`: established EMA50/200, positive 22/44/66 returns,
   volume expansion and rising daily Hull.
2. `progressive`: recovery, pullback, retest, breakout and confirmed trend with
   setup-dependent volume and structural risk.
3. `with_weekly`: adds available completed-week permission to progressive.
4. `daily_location`: adds entry location and measured resistance room.

`mature_control` is not a reconstruction of any of the four native scanners.
Hull and V3 technical results can be identical: V3 fundamentals are not invented.
Penny's technical experiment also does not certify market-cap, restriction,
circuit, ownership or fundamental eligibility. `operational_entry_ready` is
always false in generated candidate annotations.

All four arms use identical executions/exits by default, so entry changes are
not confounded with different exits. The separate revised-exits run is the exit
ablation. Trades use one original risk unit independently, not pooled capital;
there is no simulated portfolio return, borrowing or allocation claim.

Default date split: research starts 2026-01-01, later period starts 2026-06-01.
Runs are independent across the boundary, preserving open/censored trades rather
than force-closing them. This is an exploratory chronological holdout on existing
data, not an independently collected future validation period. Do not repeatedly
optimize the threshold against the reported later-period results.

Output includes strict JSON manifests, configuration hash, source coverage,
per-trade evidence, open/review/pending counts, errors, current daily annotations,
recorded Hull audit and a readable `REPORT.md`. Statistics include Wilson win-rate
intervals, expectancy, payoff, profit factor, average R, and setup/weekly groups.

## Limitations and activation boundary

- Only confirmed pivot values are available to decisions; no backdating pivots.
- Current partial weekly candles are excluded until the Friday label. With no
  exchange calendar, a holiday-ending week is conservatively available next week.
- Missing/invalid symbol sessions freeze existing research positions for review;
  large opening discontinuities do likewise. This is not a full corporate-action
  adjustment engine. Locked bars are not assumed executable.
- Stop wins on a candle reaching both stop and target; entry-bar targets are not
  credited. A candle crossing entry and stop records the adverse fill.
- Daily-only data cannot reveal exact intrabar MFE/MAE or circuit queue fills.
- Historical security-universe membership, complete corporate eligibility,
  sector valuations and adjustment coverage remain uncertified. Benchmark
  observations are not carried forward beyond their recorded dates.
- Unknown fundamentals never become a qualified operational entry. Negative
  research outcomes are retained; no thresholds auto-tune to improve the report.
- Neither an attractive win rate nor this implementation authorizes changing the
  deployed scanners. Native-strategy replay, adequate independent validation and
  a separate activation decision are still required.
