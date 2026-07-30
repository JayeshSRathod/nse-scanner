# Database Schema V2 Baseline

## Principles

- SQLite is the initial operational store.
- Schema migrations are versioned and idempotent.
- Historical source data is never silently overwritten.
- Daily market data uses a unique `(symbol, trade_date)` key.
- Every signal and position records scanner and rule-set versions.
- Monetary and quantity fields use explicit units.
- Dates are stored as ISO `YYYY-MM-DD`; timestamps are stored in UTC.

## Core tables

### `schema_version`

```text
version                 TEXT PRIMARY KEY
applied_at_utc          TEXT NOT NULL
migration_name          TEXT NOT NULL
checksum                TEXT NOT NULL
```

### `scanner_version`

```text
scanner_version         TEXT PRIMARY KEY
rule_set_version        TEXT NOT NULL
schema_version          TEXT NOT NULL
build_commit            TEXT
activated_at_utc        TEXT
status                  TEXT NOT NULL
notes                   TEXT
```

### `master_stock`

```text
symbol                  TEXT PRIMARY KEY
isin                    TEXT
company_name            TEXT
series                  TEXT
sector                  TEXT
industry                TEXT
listing_date            TEXT
delisting_date          TEXT
is_active               INTEGER NOT NULL DEFAULT 1
asm_gsm_status          TEXT
last_verified_date      TEXT
```

### `daily_price`

```text
symbol                  TEXT NOT NULL
trade_date              TEXT NOT NULL
open                    REAL NOT NULL
high                    REAL NOT NULL
low                     REAL NOT NULL
close                   REAL NOT NULL
volume                  INTEGER
turnover                REAL
delivery_qty            INTEGER
delivery_pct            REAL
source                   TEXT NOT NULL
is_adjusted              INTEGER NOT NULL DEFAULT 0
quality_status          TEXT NOT NULL DEFAULT 'UNVALIDATED'
loaded_at_utc           TEXT NOT NULL
PRIMARY KEY (symbol, trade_date)
```

### `market_index_price`

```text
index_code              TEXT NOT NULL
trade_date              TEXT NOT NULL
open                    REAL
high                    REAL
low                     REAL
close                   REAL NOT NULL
volume                  REAL
source                  TEXT NOT NULL
PRIMARY KEY (index_code, trade_date)
```

### `sector_index_price`

Same structure as `market_index_price`, keyed by `(sector_code, trade_date)`.

### `daily_indicator`

```text
symbol                  TEXT NOT NULL
trade_date              TEXT NOT NULL
hma21                   REAL
hma51                   REAL
hybrid_hull55           REAL
ma50                    REAL
ma200                   REAL
atr14                    REAL
extension_atr           REAL
relative_volume         REAL
delivery_ratio          REAL
close_location_value    REAL
rs_1m                   REAL
rs_3m                   REAL
rs_6m                   REAL
rs_percentile           REAL
sector_rs_percentile    REAL
weekly_trend_status     TEXT
daily_trend_status      TEXT
scanner_version         TEXT NOT NULL
PRIMARY KEY (symbol, trade_date, scanner_version)
```

### `market_regime_snapshot`

```text
trade_date              TEXT NOT NULL
benchmark_code          TEXT NOT NULL
regime                  TEXT NOT NULL
close_above_ma200       INTEGER
ma50_above_ma200        INTEGER
breadth_above_ma50_pct  REAL
leading_sectors_json    TEXT
lagging_sectors_json    TEXT
scanner_version         TEXT NOT NULL
PRIMARY KEY (trade_date, benchmark_code, scanner_version)
```

### `scanner_candidate`

```text
candidate_id            TEXT PRIMARY KEY
symbol                  TEXT NOT NULL
scan_date               TEXT NOT NULL
data_date               TEXT NOT NULL
setup_type              TEXT NOT NULL
candidate_status        TEXT NOT NULL
initial_horizon         TEXT NOT NULL
market_regime           TEXT
score_total             REAL NOT NULL
score_breakdown_json    TEXT NOT NULL
confidence_grade        TEXT
entry_trigger           REAL
initial_stop            REAL
target_1                REAL
target_2                REAL
risk_pct                REAL
reward_risk             REAL
invalidation_reason     TEXT
selection_reasons_json  TEXT
rejection_reasons_json  TEXT
scanner_version         TEXT NOT NULL
created_at_utc          TEXT NOT NULL
UNIQUE (symbol, scan_date, setup_type, scanner_version)
```

### `portfolio_position`

```text
trade_id                TEXT PRIMARY KEY
symbol                  TEXT NOT NULL
setup_type              TEXT NOT NULL
discovery_date          TEXT
signal_date             TEXT
entry_date              TEXT
average_entry_price     REAL
initial_quantity        REAL NOT NULL DEFAULT 0
open_quantity           REAL NOT NULL DEFAULT 0
initial_stop            REAL
current_stop            REAL
target_1                REAL
target_2                REAL
current_horizon         TEXT NOT NULL
lifecycle_state         TEXT NOT NULL
carry_forward_status    TEXT
total_cost              REAL NOT NULL DEFAULT 0
realised_pnl            REAL NOT NULL DEFAULT 0
highest_high_since_entry REAL
highest_close_since_entry REAL
market_regime_at_entry  TEXT
sector_rank_at_entry    REAL
rs_rank_at_entry        REAL
scanner_version         TEXT NOT NULL
opened_at_utc           TEXT
closed_at_utc           TEXT
exit_reason             TEXT
```

### `position_event`

```text
event_id                TEXT PRIMARY KEY
trade_id                TEXT NOT NULL
event_date              TEXT NOT NULL
event_type              TEXT NOT NULL
previous_state          TEXT
new_state               TEXT
price                   REAL
quantity                REAL
previous_value_json     TEXT
current_value_json      TEXT
reason                  TEXT
severity                TEXT
action                  TEXT
scanner_version         TEXT NOT NULL
created_at_utc          TEXT NOT NULL
```

### `horizon_qualification`

```text
trade_id                TEXT NOT NULL
qualification_date      TEXT NOT NULL
horizon                 TEXT NOT NULL
qualified               INTEGER NOT NULL
score                   REAL
criteria_json            TEXT NOT NULL
failure_reasons_json    TEXT
scanner_version         TEXT NOT NULL
PRIMARY KEY (trade_id, qualification_date, horizon, scanner_version)
```

### `daily_position_snapshot`

```text
trade_id                TEXT NOT NULL
snapshot_date           TEXT NOT NULL
current_price           REAL
current_market_value    REAL
unrealised_pnl          REAL
current_return_pct      REAL
initial_risk_amount     REAL
current_risk_amount     REAL
open_r                  REAL
realised_r              REAL
total_r                 REAL
current_horizon         TEXT
lifecycle_state         TEXT
current_stop            REAL
t1_status               TEXT
t2_status               TEXT
rs_rank                 REAL
sector_rank             REAL
trend_status            TEXT
carry_forward_status    TEXT
action                  TEXT
attention_flag          INTEGER NOT NULL DEFAULT 0
scanner_version         TEXT NOT NULL
PRIMARY KEY (trade_id, snapshot_date, scanner_version)
```

### `portfolio_daily_snapshot`

```text
portfolio_date          TEXT NOT NULL
invested_capital        REAL NOT NULL
current_market_value    REAL NOT NULL
realised_pnl            REAL NOT NULL
unrealised_pnl          REAL NOT NULL
total_pnl               REAL NOT NULL
daily_pnl               REAL
portfolio_return_pct    REAL
total_portfolio_r       REAL
average_r_per_position  REAL
open_risk_amount        REAL
open_risk_pct           REAL
protected_profit        REAL
peak_market_value       REAL
drawdown_pct            REAL
portfolio_health_score  REAL
winners_count           INTEGER
losers_count            INTEGER
flat_count              INTEGER
horizon_summary_json    TEXT
concentration_alerts_json TEXT
scanner_version         TEXT NOT NULL
PRIMARY KEY (portfolio_date, scanner_version)
```

### `telegram_delivery_log`

```text
report_date             TEXT NOT NULL
data_date               TEXT NOT NULL
message_type            TEXT NOT NULL
message_hash            TEXT NOT NULL
sent_at_utc             TEXT
telegram_message_id     TEXT
status                  TEXT NOT NULL
error_message           TEXT
scanner_version         TEXT NOT NULL
PRIMARY KEY (report_date, message_type, message_hash)
```

### `evidence_outcome`

```text
trade_id                TEXT PRIMARY KEY
setup_type              TEXT NOT NULL
entry_date              TEXT
exit_date               TEXT
holding_sessions        INTEGER
maximum_favourable_excursion_pct REAL
maximum_adverse_excursion_pct REAL
realised_return_pct     REAL
realised_r              REAL
exit_reason             TEXT
market_regime_at_entry  TEXT
sector_status_at_entry  TEXT
scanner_version         TEXT NOT NULL
closed_evidence_json    TEXT
```

## Later fundamental tables

Deferred to the fundamentals sprint:

- `quarterly_financial`
- `shareholding_pattern`
- `valuation_snapshot`
- `fundamental_quality_snapshot`

## Migration requirements

1. Back up the current database before migration.
2. Audit the approximately 420-day dataset before copying.
3. Preserve source rows and data dates.
4. Record rejected rows with explicit reasons.
5. Produce pre/post row counts and symbol/date coverage.
6. Never promote unvalidated rows to production calculations.
