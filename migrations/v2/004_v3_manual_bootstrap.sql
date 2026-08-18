-- Shareholding and corporate-action history for the V3 manual bootstrap.
CREATE TABLE IF NOT EXISTS shareholding_patterns_v3 (
 symbol TEXT NOT NULL, as_of_date TEXT NOT NULL, available_date TEXT NOT NULL,
 shares_outstanding REAL NOT NULL, promoter_holding_pct REAL,
 public_holding_pct REAL, source TEXT NOT NULL, filing_id TEXT,
 loaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(symbol,as_of_date));
CREATE TABLE IF NOT EXISTS corporate_actions_v3 (
 symbol TEXT NOT NULL, ex_date TEXT NOT NULL, available_date TEXT NOT NULL,
 action_type TEXT NOT NULL, ratio_from REAL, ratio_to REAL, description TEXT,
 source TEXT NOT NULL, filing_id TEXT,
 loaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(symbol,ex_date,action_type));
INSERT OR IGNORE INTO schema_migrations (migration_id,checksum,notes)
VALUES ('004_v3_manual_bootstrap','v1','Shareholding and corporate-action manual bootstrap');
