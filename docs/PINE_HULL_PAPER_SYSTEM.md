# Pine Hull EOD Paper System

This is an isolated, long-only paper-trading subsystem. It reads existing NSE
daily snapshots and does not alter V2 candidates, V2 portfolio state, or V2
Telegram messages.

## Fixed EOD core

- Hybrid Hull 55
- HMA21 / HMA51
- ATR14 × 3.5
- KAMA30
- Daily trend-commitment, extension, chop, rotation, EMA/RSI/ADX, and volume checks
- Weekly HMA21/HMA51 carry-forward context

The implementation intentionally excludes all intraday-only Pine features:
Developing POC/VAH/VAL, gap projections, lower-timeframe volume profile,
ZigZag/order-block imports, auto trendlines, and chart-only visuals.

## Persistent files

- `pine_hull_state.json`: Pine-only paper positions, frozen entry/SL/T1/T2, events, and P&L.
- `output/pine_hull_daily_run.json`: latest daily result and delivery status.

The Pine portfolio uses a separate ₹3,00,000 virtual capital base by default;
it must never be combined with V2 capital or P&L.

## Telegram secrets

The existing `TELEGRAM_TOKEN` and `TELEGRAM_CHAT_ID` are reused. Create new
forum Topics and store their numeric IDs as GitHub Actions secrets:

```text
TELEGRAM_PINE_SIGNALS_TOPIC_ID
TELEGRAM_PINE_PORTFOLIO_TOPIC_ID
TELEGRAM_PINE_WEEKLY_TOPIC_ID
TELEGRAM_PINE_MONTHLY_TOPIC_ID
```

Missing Topic IDs do not stop the workflow; Telegram delivery falls back to the
group's general chat, so configure them before enabling manual production runs.

## Scheduling

`pine-hull-daily.yml` runs only after a successful `NSE Pipeline Daily Run`,
then commits its own state. Weekly and monthly workflows send independent
Pine-labelled reports. None invokes `main_pipeline.py` or V2 orchestration.

## EOD limitation

The system observes a stop or exit only after a completed daily bar. It reports
the protective level for manual trading; it does not place broker orders or
provide intraday stop execution.
