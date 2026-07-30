# Sprint 4 Status — Persistent Trade Lifecycle

## Completed

- Permanent UUID trade IDs.
- WATCH, READY, OPEN, PARTIAL, TRAILING, CLOSED and CANCELLED states.
- SQLite persistence for positions, event history and watchlist memory.
- Daily completed-bar processor for all active positions.
- Conservative same-bar execution policy: protective stop wins when target/stop ordering is unknowable.
- Entry-trigger and stop collision handling.
- T1 partial exit and T2 final exit handling.
- Horizon-specific ATR trailing stops:
  - SWING_1_3M: 2.0 ATR
  - POSITIONAL_3_6M: 2.5 ATR
  - POSITIONAL_6_12M: 3.0 ATR
- Stops are monotonic and cannot move backward.
- WATCH/READY invalidation and cancellation.
- Carry-forward MARK events when no transition occurs.
- Watchlist deactivation only after explicit CLOSED or CANCELLED state.
- Message 2 renderer for active and newly terminal positions.
- Unit tests and isolated GitHub Actions workflow.

## Daily processing order

1. Cancel invalid WATCH/READY setups.
2. Qualify WATCH positions.
3. Trigger READY entries when the bar high reaches entry.
4. Apply same-bar entry/stop collision conservatively.
5. For active positions, process stop before targets.
6. Process T1 partial exit.
7. Process T2 final exit.
8. Advance the horizon-specific ATR trailing stop.
9. Otherwise persist a carry-forward MARK event.

## Explicit limitation

Daily OHLC bars do not reveal intraday event order. Where both a stop and target are inside one bar, the engine assumes the adverse stop-first path. This prevents optimistic backtest and live-accounting bias.

## Sprint 4 completion gate

Sprint 4 is code-complete. Integration with the daily scanner runner and Telegram delivery belongs to Sprint 5, while full historical lifecycle outcome validation belongs to Sprint 7.
