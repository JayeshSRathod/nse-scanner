# Uniform paper portfolio accounting

Implementation branch: `codex/uniform-paper-portfolios`.
Rollout status: **offline validation; scheduled delivery remains unchanged**.

## Contract

Each scanner retains its signal selection, stop and target logic. The common
snapshot records starting capital, available cash, invested capital at cost,
pending reservations, holdings value, gross booked/open P&L, recorded fees,
total P&L, equity and return on starting capital. All quantities and cash remain
separate by scanner. This is simulated accounting, never a broker instruction.

For remaining quantity q and entry e: invested capital = sum(q * e).
Unrealised P&L = sum(q * (mark - e)). Realised P&L includes booked partial exits
as well as fully closed trades. Available cash = starting capital + realised
P&L - fees - invested capital. Equity = cash + holdings value = starting capital
+ total P&L. Pending entries have no market value or P&L; reservations are shown
separately. A closed trade has zero remaining quantity. Returns use starting
capital, never the sum or average of individual stock returns.

Amounts are kept unrounded internally. Rendering rounds to two decimals.
Non-finite amounts, duplicate trade IDs and impossible quantities fail closed.
Records with insufficient quantity/fill evidence are retained as legacy records,
excluded from accounting totals and explicitly disclosed. Missing marks remain
at the last recorded price with a provisional valuation warning. Review holdings
remain invested until a supported corporate action or exit resolves them.

## Scanner reconciliation

| Scanner | Integration | Preserved behaviour / limitation |
| --- | --- | --- |
| Hull (`pine_hull`) | Read native positions through common adapter | Existing full-quantity exits and target milestones; no invented partial sales. New marks carry dates. Older undated marks are disclosed. |
| V3 (`v2`) | Read SQLite positions and entry events | Existing partial quantities and realised proceeds; WATCH/READY reservations separate from invested capital. Native recorded fills remain unchanged. |
| Momentum Ladder (`old_nse_hull`) | Separate persistent quantity ledger fed by existing multi-horizon shadow candidates and levels | T1 is a milestone; T2/stop closes the position. The old tracker does not implement its descriptive trailing rule; the new ledger does not silently invent it. Legacy tracker remains untouched. |
| Penny | Separate persistent ledger fed only by current READY candidates | Reuses the earlier local implementation's next-session lifecycle, five-session expiry and T1 break-even stop concept. It does not replace current progressive selection with the older scanner. |

The local `main` commits `b97d1f1` and `2ce3e43` remain preserved. Their lifecycle
was reconciled conceptually, not blindly cherry-picked: the current signal model,
Telegram routes and shared tradeability gates differ from that older branch.
The old local DB tables and JSON state files are not migrated or overwritten.

## Explicit execution assumptions

The new Penny/Ladder cohort uses integer quantities, starting capital ₹300,000,
1% capital risk per position, 20% maximum position allocation, 5% aggregate
initial-downside risk and eight open/pending slots. These are **new accounting
cohort settings**, not a claim that old event-only trades used those quantities.

Signals are staged after the completed daily bar; they cannot fill that day.
Later fills use max(open, trigger), plus configurable slippage, capped by the
Penny entry range / a 3% Ladder trigger allowance. A greater than 3% opening gap
is skipped. Risk geometry is rechecked at the actual simulated fill. Stops fill
at min(open, stop), less configured slippage. On a stop/target collision the stop
wins; on an entry bar no favourable target fill is inferred. A one-price bar or
the existing-style candle circuit proxy blocks assumed fills. This is conservative
OHLC modelling, not proof of exchange circuit status or available liquidity.

Penny expires after five subsequent market sessions. Ladder preserves the old
tracker's no-expiry behaviour. Both allow a later, fresh signal after a closed
trade, but not on the same exit day. Pending orders reserve slots but no cash;
all cash/risk limits are enforced sequentially at actual fill time.

Fees and slippage default to zero and are configurable on the ledger API.
Zero-fee reports explicitly say gross. Native Hull/V3 records do not provide a
complete historical fee model. Their fill models are named in every JSON report:
**uniform accounting is not yet identical execution or a fair performance ranking**.
No strategy timing filters have been shortened in this project.

SQLite transactions prevent concurrent duplicate fills; each session is immutable.
Identical retries return the stored report. Changed session inputs, changed ledger
settings and out-of-order dates fail and require a separate reconstruction ledger.
SQLite is closed before the report is exported; a report failure can be retried
without repeating fills. Keep the ledger files when restarting a runner.

## Opt-in integration and offline review

All four scanner commands accept `--uniform-portfolio-dir DIRECTORY`. Without
that flag their existing delivery paths remain active. Penny/Ladder keep separate
SQLite files in that directory; Hull/V3 adapt their native records. Ladder also
requires `--multi-horizon-shadow`. Opting in replaces the relevant portfolio
message with the common report, using existing scanner-specific routes. Do not
run the scanner commands against production state merely to preview the format.

For a read-only native audit and a separate Penny/Ladder cohort:

```text
python scripts/review_uniform_portfolios.py --db COPY_OF_MARKET.db --output output/uniform_review
```

The command never sends messages. It reads Hull state and existing signal reports,
does not advance Hull/V3 strategies, and writes only the new review directory.
Specify `--hull-state`, `--penny-report`, `--ladder-report`, `--ladder-legacy` when
reviewing copied snapshots. Signal dates must exist in the selected database.
If the V3 database lacks a capital snapshot, supply the recorded `--v3-capital`.
Do not infer a historical V3 portfolio from today's mutable positions.

## Approval and rollout

Before enabling scheduled delivery: review the generated examples and cohort
starting date, confirm legacy exclusions and capital, preserve native state, and
enable the opt-in flag. GitHub runners must restore/persist each scanner's SQLite
ledger along with its generated report; without that persistence, do not enable
the new Penny/Ladder portfolio. Keep separate ledgers for offline reconstruction
and scheduled cohorts. Never replay reconstructed positions into the live paper
ledger. The user approval checkpoint is the completed offline result, not an
intermediate coding decision.

The four scheduled workflows are prepared to read the repository variable
`UNIFORM_PAPER_PORTFOLIOS` (default false). When enabled, they restore the committed
`paper_portfolios` directory with checkout and persist only their own ledger and
report files. No repository variable is changed by implementation or validation.
V3's pipeline entrypoint uses the same switch. Native Hull's opt-in allocation
also deducts recorded realised losses/fees and reserves review holdings, so it
cannot keep allocating the original capital after losses. Existing negative-cash
history is disclosed rather than silently recast or recapitalised.

After activation monitor five completed trading sessions: cash/equity
reconciliation, missing marks, event counts, rerun consistency and route isolation.
This monitoring is an operational check, not evidence of strategy profitability.
