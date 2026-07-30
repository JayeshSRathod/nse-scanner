-- V2 Sprint 1: additive data-foundation schema.
-- Safe to run repeatedly. Existing V1 tables and rows are not deleted.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_id TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    checksum TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS scanner_versions (
    version_id TEXT PRIMARY KEY,
    ruleset_name TEXT NOT NULL,
    schema_version INTEGER NOT NULL,
    activated_at TEXT,
    retired_at TEXT,
    status TEXT NOT NULL DEFAULT 'DEVELOPMENT',
    config_hash TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS data_quality_runs (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    audited_at TEXT NOT NULL,
    database_path TEXT NOT NULL,
    status TEXT NOT NULL,
    oldest_date DATE,
    newest_date DATE,
    session_count INTEGER,
    symbol_count INTEGER,
    row_count INTEGER,
    error_count INTEGER NOT NULL DEFAULT 0,
    warning_count INTEGER NOT NULL DEFAULT 0,
    report_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trading_sessions (
    trade_date DATE PRIMARY KEY,
    exchange TEXT NOT NULL DEFAULT 'NSE',
    is_trading_day INTEGER NOT NULL DEFAULT 1 CHECK (is_trading_day IN (0,1)),
    session_status TEXT NOT NULL DEFAULT 'COMPLETE',
    source TEXT,
    loaded_at TEXT,
    validated_at TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS symbol_master_v2 (
    symbol TEXT PRIMARY KEY,
    isin TEXT,
    company_name TEXT,
    series TEXT,
    sector TEXT,
    industry TEXT,
    listing_date DATE,
    delisting_date DATE,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS daily_prices_v2 (
    symbol TEXT NOT NULL,
    trade_date DATE NOT NULL,
    prev_close REAL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    last_price REAL,
    close REAL NOT NULL,
    avg_price REAL,
    volume INTEGER,
    turnover_lacs REAL,
    trades INTEGER,
    delivery_qty INTEGER,
    delivery_pct REAL,
    source TEXT NOT NULL DEFAULT 'NSE',
    source_loaded_at TEXT,
    quality_status TEXT NOT NULL DEFAULT 'UNVALIDATED',
    PRIMARY KEY (symbol, trade_date),
    CHECK (high >= low),
    CHECK (high >= open AND high >= close),
    CHECK (low <= open AND low <= close),
    CHECK (close > 0),
    CHECK (volume IS NULL OR volume >= 0),
    CHECK (delivery_pct IS NULL OR (delivery_pct >= 0 AND delivery_pct <= 100))
);

CREATE INDEX IF NOT EXISTS idx_daily_prices_v2_date
    ON daily_prices_v2(trade_date);
CREATE INDEX IF NOT EXISTS idx_daily_prices_v2_symbol
    ON daily_prices_v2(symbol);
CREATE INDEX IF NOT EXISTS idx_daily_prices_v2_quality
    ON daily_prices_v2(quality_status, trade_date);

CREATE TABLE IF NOT EXISTS migration_reconciliation (
    reconciliation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    migration_id TEXT NOT NULL,
    reconciled_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_table TEXT NOT NULL,
    target_table TEXT NOT NULL,
    source_rows INTEGER,
    target_rows INTEGER,
    source_min_date DATE,
    source_max_date DATE,
    target_min_date DATE,
    target_max_date DATE,
    duplicate_rows INTEGER,
    invalid_rows INTEGER,
    status TEXT NOT NULL,
    details_json TEXT
);

INSERT OR IGNORE INTO scanner_versions (
    version_id, ruleset_name, schema_version, status, notes
) VALUES (
    '2.0.0-dev', 'multi-horizon-v2', 1, 'DEVELOPMENT',
    'Sprint 1 additive data-foundation baseline'
);
