# NSE Scanner V2 Changelog

All material architecture, rule, schema and reporting changes must be recorded here.

## [0.0.1] - 2026-07-29

### Added

- Created V2 integration branch `develop/v2-multi-horizon` from production `main`.
- Added V2 architecture baseline.
- Added Sprint 0 production and migration controls.
- Added initial V2 database schema.
- Added Sprint 0-8 implementation roadmap and acceptance gates.

### Decisions frozen

- Reuse the current repository rather than create a new repository.
- Keep V1 production on `main` during V2 development.
- Reuse and validate the existing approximately 420-trading-day NSE history.
- Append only missing completed trading sessions during normal operation.
- Use a continuous lifecycle from discovery through 1M, 3M, 6M and 12M qualification.
- Deliver three Telegram messages: fresh scanner, portfolio lifecycle and portfolio P&L/risk.
- Require fundamentals before labelling 6M/12M candidates as investment-grade.
- Require live and backtest logic to use the same calculation functions.

### Production impact

None. Sprint 0 documentation is isolated on the V2 development branch.
