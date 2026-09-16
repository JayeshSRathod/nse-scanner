# Portfolio implementation review — 12 September 2026

Status: implemented on an isolated branch; scheduled delivery not activated.
No Telegram messages, broker calls, merges or live portfolio migrations were
performed during the offline review.

## Current recorded portfolios

Source: GitHub baseline `7e74624d6fe457e4b51ab829e21371045719df6f`.
Market data was restored into a separate SQLite copy through 10 September 2026;
the user's source database and native state files were preserved. V3 state was
restored into that copy from the Git-backed `v2_portfolio_state.json`.

| Scanner | Evidence date | Open | Pending | Available cash | Total P&L | Equity |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Hull, native records | 2026-09-10 | 8 | 0 | -₹9,591.06 | -₹3,291.66 | ₹296,708.34 |
| V3, native records | 2026-09-10 | 0 | 0 | ₹300,000.00 | ₹0.00 | ₹300,000.00 |
| Penny, new review cohort | 2026-09-10 | 0 | 0 | ₹300,000.00 | ₹0.00 | ₹300,000.00 |
| Ladder, new review cohort | 2026-09-10 | 0 | 8 | ₹300,000.00 | ₹0.00 | ₹300,000.00 |

Penny/Ladder rows are new isolated accounting cohorts, not reconstructed historical
holdings. Pending Ladder orders do not consume cash or create returns. The latest
Penny report contained no READY entries; the zero portfolio is not proof of a
profitable or unprofitable strategy.

Hull's recorded positions imply negative cash against its stated capital, and
older marks lack per-position dates. These are disclosed in the new report.
Historical records were not silently rewritten. The opt-in Hull allocator now
deducts realised losses/fees and reserves review holdings before sizing a new
position. Future rollouts must preserve this historical reconciliation warning.

## Archived-signal reconstruction

`scripts/replay_uniform_portfolios.py` replayed immutable Git signal reports into
separate Penny/Ladder accounting ledgers, with the selected local metadata
snapshot. This verifies accounting/execution on observed archived signals; it is
not a point-in-time universe backtest or a comparison of scanner profitability.

| Scanner | Window | Sessions | Simulated entries | Stop exits | Final open | Final pending | Final equity |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Penny | 2026-08-25 to 2026-09-10 | 13 | 0 | 0 | 0 | 0 | ₹300,000.00 |
| Momentum Ladder | 2026-08-26 to 2026-09-10 | 12 | 4 | 1 | 3 | 5 | ₹295,835.07 |

Every session reconciled cash + market value to starting capital + P&L, with
maximum floating-point residual below ₹0.000000001. Gross zero-cost assumptions
are labelled; native Hull/V3 fill models are different and not retrospectively
replaced. No reconstructed positions were copied into scheduled paper state.

## Validation and artifacts

The final full suite passed **259 tests** (55.91 seconds), including native
Hull/V3 retry safety and the default-off rollout switch. Earlier suite attempts
hit Windows temporary-directory access and missing dependency errors; those were
environment failures resolved using an isolated dependency folder and a fresh
test directory. Workflow YAML parsing and `git diff --check` also passed.

Scenario tests cover partial exit proceeds, pending reservations, stop/target
collisions, opening gaps, circuit proxies, stale marks, corporate-action review
holdings, fees, cash/risk limits, concurrent retries, transaction rollback,
changed historical inputs and missing market sessions. HTML messages escape
symbols and paginate below the existing delivery limit.

Local review artifacts:

- `output/uniform_portfolio_validation/current/audit.json`
- `output/uniform_portfolio_validation/current/{hull,v3,penny,momentum_ladder}.html`
- `output/uniform_portfolio_validation/replay_verified/replay_evidence.json`
- `output/uniform_portfolio_validation/replay_verified/latest/`

Activation is prepared through the repository variable `UNIFORM_PAPER_PORTFOLIOS`.
It defaults to false. After approval and merge, setting it true enables the common
reports and scanner-specific ledger persistence. Use a fresh forward cohort for
Penny/Ladder, retain historical warnings for Hull, and monitor five completed
trading sessions. V8 and entry-confirmation tuning remain outside this change.
