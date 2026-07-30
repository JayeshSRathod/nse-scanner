# NSE Scanner V2 Architecture

## Status

Sprint 0 architecture baseline for `develop/v2-multi-horizon`.

The production `main` branch remains the V1 operational baseline until V2 completes parallel validation and production cutover.

## Product definition

V2 is a multi-horizon breakout discovery, portfolio lifecycle and performance-management system.

It follows one continuous state progression:

```text
DISCOVERY
  -> WATCH_NEAR_BREAKOUT
  -> TRIGGER_PENDING
  -> ENTRY_TRIGGERED
  -> ACTIVE_1M
  -> QUALIFIED_3M
  -> QUALIFIED_6M
  -> QUALIFIED_12M
  -> TRAILING / REDUCE / EXIT
```

Time alone never promotes a position. Every horizon requires positive requalification.

## Core engines

1. Data and quality engine
2. Market regime engine
3. Sector and relative-strength engine
4. Technical setup engine
5. Multi-horizon qualification engine
6. Portfolio lifecycle engine
7. P&L and risk engine
8. Evidence and performance engine
9. Telegram reporting engine
10. Automation and delivery engine

## Data strategy

The existing approximately 420-trading-day NSE database is the historical seed. V2 must validate and migrate it; it must not redownload the full history unless audit results show material gaps or corruption.

Normal operation is incremental:

```text
latest stored trading date
  -> identify missing completed NSE sessions
  -> download only missing sessions
  -> validate
  -> upsert using symbol + trade_date
  -> calculate indicators and reports
```

A controlled repair mode may refresh a small recent window. A full rebuild is exceptional.

## Scanner layers

```text
Universe
  -> data and liquidity validation
  -> market regime
  -> sector strength
  -> stock relative strength
  -> weekly trend permission
  -> setup classification
       - breakout
       - pullback
       - compression
  -> volume and delivery confirmation
  -> ATR extension and risk validation
  -> resistance-aware entry, stop and targets
  -> PRIME / WATCH / AVOID
  -> independent position lifecycle
```

## Hard filters

Initial V2 design:

- minimum 260 valid sessions for full-history qualification;
- price at least INR 50;
- 20-day median turnover at least INR 5 crore;
- 20-day median volume at least 100,000 shares, with turnover taking priority for high-priced stocks;
- valid OHLC mandatory;
- delivery availability mandatory for PRIME;
- missing weekly history means insufficient data;
- ASM/GSM/IRP exclusions when reliable status data is available.

## Primary indicators

Retain as decision inputs:

- weekly HMA21/HMA51;
- daily Hybrid Hull 55;
- MA200 regime reference;
- ATR14;
- stock relative strength versus benchmark;
- dynamic sector relative strength;
- volume and delivery participation.

RSI, MACD, KAMA and 52-week position may remain as explanatory display fields but must not duplicate the primary score.

## Technical setups

### Breakout

Established trend, breakout through defined resistance, relative volume and delivery confirmation, strong close location, acceptable ATR extension and resistance-aware reward/risk.

### Pullback continuation

Weekly and daily trend alignment, controlled pullback near Hull, lighter pullback volume, reversal confirmation and structure-based stop.

### Compression breakout

Trend alignment, volatility contraction, narrowing range, drying volume and breakout from the compression range with participation confirmation.

## Market regime

- RISK_ON: benchmark above MA200, MA50 above MA200 and breadth at or above 55% above MA50.
- NEUTRAL: benchmark above MA200 with breadth between 40% and 55%.
- RISK_OFF: benchmark below MA200 or breadth below 40%.

Risk-off blocks fresh momentum PRIME entries unless a later rule version explicitly permits defensive exceptions.

## Scoring

Transparent 100-point model:

| Factor | Points |
|---|---:|
| Market regime | 10 |
| Stock relative strength | 20 |
| Sector relative strength | 10 |
| Weekly trend | 15 |
| Daily Hull trend | 10 |
| Setup quality | 15 |
| Volume and delivery | 10 |
| Volatility and extension | 5 |
| Liquidity | 5 |
| Total | 100 |

Hard overrides supersede the score.

## Portfolio lifecycle

Each position requires a persistent trade ID and event history. Leaving the daily top list is not an exit condition.

Core states:

```text
DISCOVERED
WATCH_NEAR_BREAKOUT
TRIGGER_PENDING
ENTRY_TRIGGERED
ACTIVE_1M
T1_HIT
T2_HIT
QUALIFIED_3M
QUALIFIED_6M
QUALIFIED_12M
TRAILING
PARTIAL_EXIT
EXIT_PENDING
EXITED
INVALIDATED
```

Actions:

```text
HOLD
CARRY_FORWARD
ADD_ON_PULLBACK
TRAIL
BOOK_25
BOOK_50
DO_NOT_ADD
REDUCE
EXIT
ATTENTION
```

## Telegram output

Three messages per trading day after freshness and holiday validation:

1. Fresh scanner output grouped by 1M, 3M, 6M and 12M.
2. Portfolio lifecycle, carry-forward status, changes and required actions.
3. Portfolio P&L, R-multiples, risk, concentration and drawdown summary.

No stale recommendation may be resent. Delivery must be idempotent.

## Fundamentals boundary

OHLCV-only candidates for six and twelve months must initially be labelled technical-only. Investment-grade 6M and 12M qualification requires a later fundamental layer covering growth, profitability, balance-sheet strength, cash flow, promoter pledge, governance and valuation.

## Versioning

Every signal, position, event, snapshot and backtest result must store:

- scanner version;
- rule-set version;
- database schema version;
- calculation date;
- source-data date.

## Production migration

1. Build V2 only on `develop/v2-multi-horizon` and feature branches.
2. Preserve V1 `main` unchanged during construction.
3. Run V1 and V2 in parallel for at least 15-20 trading sessions.
4. Reconcile candidates, lifecycle decisions, P&L and message delivery.
5. Create a final V1 archive branch/tag before cutover.
6. Merge V2 into `main` only after a documented go/no-go review.
7. Retain an immediate rollback path.
