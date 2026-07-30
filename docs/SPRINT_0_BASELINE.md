# Sprint 0 Baseline and Controls

## Objective

Protect the operational V1 system and establish a controlled V2 development baseline without changing production scanner logic, production workflows or production Telegram delivery.

## Branch policy

- `main`: current V1 production baseline.
- `develop/v2-multi-horizon`: V2 integration branch.
- `feature/v2-*`: focused implementation branches created from the V2 integration branch.
- Final merge direction: `develop/v2-multi-horizon` into `main` after validation.

No V2 feature work should be committed directly to `main`.

## Production safety rules

1. V2 workflows must not use the production Telegram destination during development.
2. V2 scheduled workflows should remain disabled or dry-run-only until their outputs pass review.
3. Existing database and output files must not be destructively migrated in place.
4. Database migration must create a backup and produce a migration audit.
5. Existing 420-day market history is reused as the seed dataset.
6. Full historical redownload is prohibited by default.
7. Every write process must be idempotent.
8. GitHub Actions database writers must use concurrency controls.
9. Stale data blocks recommendations.
10. V1 remains the rollback route until post-cutover monitoring is complete.

## Sprint 0 accepted decisions

- Repository: reuse `JayeshSRathod/nse-scanner`.
- Deployment model: existing repository plus protected V2 branch.
- Price history: reuse and validate approximately 420 trading days.
- Data refresh: append only missing completed trading sessions.
- Live broker dependency: none for V2 core.
- Telegram: three daily reports.
- Lifecycle: one continuous state machine across 1M, 3M, 6M and 12M.
- Fundamentals: separate later layer for investment-grade 6M/12M qualification.
- Backtest: must call the same calculation functions as production.

## Required baseline capture before Sprint 1 code migration

Sprint 1 must inventory and record:

- current repository tree;
- current workflow files, schedules and permissions;
- current secrets by name only, never values;
- current database file path and schema;
- current historical date range and row counts;
- duplicate and missing-date statistics;
- current production output files;
- one sample of each current Telegram message;
- current indicator implementations;
- current scoring and ranking functions;
- current holiday and freshness checks;
- current automated commit behaviour.

## Sprint 0 definition of done

- V2 integration branch created.
- V2 architecture documented.
- migration and production safety rules documented.
- sprint roadmap documented.
- initial database schema documented.
- V2 changelog initialized.
- production `main` unchanged by Sprint 0 documentation work.

## Deferred until production cutover

The final archive branch/tag should be created immediately before V2 production cutover so it identifies the actual last V1 production commit, rather than the earlier Sprint 0 baseline.
