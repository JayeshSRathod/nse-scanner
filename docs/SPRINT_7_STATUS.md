# Sprint 7 — Point-in-Time Validation

## Objective

Validate V2 candidates using only data available on each historical scan date. Reuse the production lifecycle processor so historical and live execution assumptions remain aligned.

## Implemented

- point-in-time candidate evaluation
- one active position per symbol
- configurable portfolio capacity
- conservative daily OHLC execution
- T1 partial exit and T2/SL final exit accounting
- ATR-based trailing stops
- trade outcomes in initial-risk units (R)
- win rate, expectancy, profit factor and cumulative R
- maximum drawdown in R
- score-threshold sensitivity
- anchored walk-forward threshold selection
- CSV/JSON reporting CLI
- deterministic synthetic-data tests

## Execution assumptions

- signal is created only after the completed signal-date bar
- the position can qualify or enter only on a subsequent completed bar
- stop wins when stop and target are both touched in the same daily bar
- entry and stop on the same bar is treated as an entered losing trade
- no slippage, brokerage, taxes or liquidity impact are included yet
- delisted and survivorship-bias controls depend on the supplied historical universe

## Command

```bash
python scripts/run_v2_validation.py --db nse_scanner.db --walk-forward
```

Outputs:

```text
output/v2_validation/
├── trades.csv
├── performance.json
├── score_sensitivity.json
└── walk_forward.json
```

## Promotion gate

Do not promote V2 signals to production-qualified status solely because aggregate backtest expectancy is positive. Review:

1. number of entered trades
2. performance by setup and horizon
3. out-of-sample walk-forward expectancy
4. maximum drawdown
5. threshold stability
6. concentration by symbol and market regime
7. transaction-cost sensitivity
8. survivorship and look-ahead controls

Sprint 7 provides the validation machinery. A real database run and review of generated artifacts remains required before parameter lock.
