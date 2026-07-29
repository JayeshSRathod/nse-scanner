# NSE Scanner V2 Roadmap

## Sprint 0 — Foundation and protection

Status: in progress

Deliverables:

- protected V2 integration branch;
- architecture baseline;
- production and migration controls;
- initial database schema;
- sprint roadmap;
- changelog initialization.

Exit gate:

- documentation is committed on V2 branch;
- `main` has no Sprint 0 changes;
- V2 production Telegram access is prohibited;
- existing 420-day dataset is formally designated as the seed history.

## Sprint 1 — Data foundation

Deliverables:

- repository and workflow inventory;
- current database schema extraction;
- 420-day data-quality audit;
- V2 schema migrations;
- historical data migration without full redownload;
- incremental update and recent-window repair modes;
- freshness, duplicate and missing-session controls.

Exit gate:

- migrated data reconciles to the source database;
- primary-key and quality checks pass;
- no destructive change to V1 data;
- repeat execution is idempotent.

## Sprint 2 — Regime, indicators and relative strength

Deliverables:

- unified HMA and Hybrid Hull calculations;
- ATR and extension measures;
- benchmark and sector index history;
- breadth-based market regime;
- stock and sector relative-strength rankings;
- removal of static sector bias from V2 logic.

Exit gate:

- indicator unit tests pass;
- sample symbols reconcile against independent calculations;
- regime output is date-explicit and reproducible.

## Sprint 3 — Setup and fresh-scanner engine

Deliverables:

- breakout, pullback and compression detectors;
- volume/delivery participation metrics;
- resistance-aware entry, stop and targets;
- transparent scoring and hard overrides;
- Message 1 preview grouped by horizon.

Exit gate:

- each candidate has reasons for and against selection;
- risk/reward and extension constraints are enforced;
- stale data cannot produce candidates.

## Sprint 4 — Portfolio lifecycle

Deliverables:

- persistent trade IDs;
- watchlist memory;
- state machine and position events;
- carry-forward qualification;
- partial exits and horizon-specific trailing stops;
- Message 2 preview.

Exit gate:

- leaving the shortlist never causes an automatic exit;
- every state transition is auditable;
- all actions have explicit reasons.

## Sprint 5 — P&L and portfolio risk

Deliverables:

- realised and unrealised P&L;
- partial-exit cost-basis treatment;
- open, realised and total R;
- horizon P&L;
- concentration, drawdown and health metrics;
- Message 3 preview.

Exit gate:

- P&L reconciles against controlled test cases;
- position and portfolio totals tie out;
- risk to current stops is correctly measured.

## Sprint 6 — Fundamentals

Deliverables:

- quarterly financial data model;
- growth, profitability, leverage, cash-flow and promoter-pledge checks;
- valuation snapshots;
- technical versus investment score;
- genuine 6M/12M investment qualification.

Exit gate:

- data age and missing fields are visible;
- technical-only candidates cannot be mislabelled investment-grade.

## Sprint 7 — Backtest and evidence engine

Deliverables:

- production/backtest function reuse;
- point-in-time simulation;
- lifecycle, target, trailing and partial-exit simulation;
- setup and regime analytics;
- walk-forward validation;
- scanner version comparison.

Exit gate:

- no look-ahead bias in reviewed test cases;
- backtest rules match production rules;
- go/no-go report completed.

## Sprint 8 — Production migration

Deliverables:

- V1/V2 parallel operation for at least 15-20 trading sessions;
- candidate, lifecycle, P&L and delivery reconciliation;
- final V1 archive branch/tag;
- V2 merge to `main`;
- old workflow disablement;
- rollback instructions.

Exit gate:

- morning delivery is fresh, idempotent and holiday-aware;
- all three messages reconcile to database records;
- rollback has been tested or dry-run validated.
