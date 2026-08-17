-- Point-in-time NSE corporate data. available_date prevents look-ahead bias.
CREATE TABLE IF NOT EXISTS corporate_filings_v3 (
 filing_id TEXT PRIMARY KEY, symbol TEXT NOT NULL, filing_type TEXT NOT NULL,
 period_end_date TEXT, available_date TEXT NOT NULL, source_url TEXT, raw_path TEXT,
 parser_version TEXT, loaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS shares_outstanding_v3 (
 symbol TEXT NOT NULL, as_of_date TEXT NOT NULL, available_date TEXT NOT NULL,
 shares_outstanding REAL NOT NULL, source TEXT NOT NULL, filing_id TEXT,
 loaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(symbol,as_of_date,available_date));
CREATE TABLE IF NOT EXISTS market_cap_snapshots_v3 (
 symbol TEXT NOT NULL, as_of_date TEXT NOT NULL, available_date TEXT NOT NULL,
 market_cap_cr REAL NOT NULL, source TEXT NOT NULL, filing_id TEXT,
 loaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(symbol,as_of_date,source));
CREATE TABLE IF NOT EXISTS promoter_pledge_v3 (
 symbol TEXT NOT NULL, as_of_date TEXT NOT NULL, available_date TEXT NOT NULL,
 pledge_pct REAL NOT NULL, event_type TEXT NOT NULL, source TEXT NOT NULL, filing_id TEXT,
 loaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(symbol,as_of_date,event_type));
CREATE TABLE IF NOT EXISTS governance_events_v3 (
 symbol TEXT NOT NULL, event_date TEXT NOT NULL, available_date TEXT NOT NULL,
 event_type TEXT NOT NULL, severity TEXT NOT NULL CHECK(severity IN ('REVIEW','SEVERE')),
 summary TEXT, source TEXT NOT NULL, filing_id TEXT, resolved INTEGER NOT NULL DEFAULT 0,
 loaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(symbol,event_date,event_type));
INSERT OR IGNORE INTO schema_migrations (migration_id,checksum,notes)
VALUES ('003_nse_corporate_data','v1','Point-in-time NSE corporate filing archive');
