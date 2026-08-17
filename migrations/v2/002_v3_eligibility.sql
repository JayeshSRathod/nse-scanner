-- V3 progressive-scanner eligibility and audit foundation.
PRAGMA foreign_keys = ON;

-- SQLite does not support ADD COLUMN IF NOT EXISTS. The daily orchestrator and
-- metadata importer add market_cap_cr/market_cap_as_of idempotently.

CREATE TABLE IF NOT EXISTS regulatory_restrictions_v2 (
    symbol TEXT NOT NULL,
    trade_date DATE NOT NULL,
    restriction_type TEXT NOT NULL,
    reason TEXT,
    source TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
    loaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(symbol, trade_date, restriction_type)
);

CREATE TABLE IF NOT EXISTS v3_eligibility_audit (
    symbol TEXT NOT NULL,
    trade_date DATE NOT NULL,
    eligible INTEGER NOT NULL CHECK (eligible IN (0,1)),
    stage TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    actual_value TEXT,
    required_value TEXT,
    metrics_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(symbol, trade_date)
);

INSERT OR IGNORE INTO schema_migrations (migration_id, checksum, notes)
VALUES ('002_v3_eligibility', 'v1', 'Market-cap, regulatory restriction and eligibility audit foundation');
