"""Readiness gate for V3 daily discovery, distinct from full backtest readiness."""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import date
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from v2.corporate_data import market_cap_max_age_days


@dataclass(frozen=True)
class OperationalReadiness:
    status: str
    price_sessions: int
    index_sessions: int
    eq_symbols: int
    market_cap_symbols: int
    market_cap_coverage_pct: float
    fundamental_symbols: int
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]


def audit(db_path: str, min_sessions: int = 400, min_cap_coverage: float = 80.0, as_of: str | None = None) -> OperationalReadiness:
    blockers, warnings = [], []
    with sqlite3.connect(db_path) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        price_table = "daily_prices_v2" if "daily_prices_v2" in tables else "daily_prices" if "daily_prices" in tables else None
        if not price_table:
            return OperationalReadiness("BLOCKED", 0, 0, 0, 0, 0, 0, ("price_table_missing",), ())
        date_col = "trade_date" if price_table == "daily_prices_v2" else "date"
        prices = conn.execute(f"SELECT COUNT(DISTINCT {date_col}) FROM {price_table}").fetchone()[0]
        indices = conn.execute("SELECT COUNT(DISTINCT date) FROM index_perf").fetchone()[0] if "index_perf" in tables else 0
        eq = caps = fundamentals = 0
        if "symbol_master_v2" in tables:
            columns = {r[1] for r in conn.execute("PRAGMA table_info(symbol_master_v2)")}
            eq = conn.execute("SELECT COUNT(*) FROM symbol_master_v2 WHERE series='EQ' AND active=1").fetchone()[0]
            if {"market_cap_cr", "market_cap_as_of", "market_cap_source"}.issubset(columns):
                cap_rows = conn.execute("SELECT market_cap_as_of,market_cap_source FROM symbol_master_v2 WHERE series='EQ' AND active=1 AND market_cap_cr IS NOT NULL").fetchall()
                reference = pd.Timestamp(as_of or date.today().isoformat()).normalize()
                caps = sum(
                    1 for cap_date, source in cap_rows
                    if cap_date and 0 <= (reference - pd.Timestamp(cap_date).normalize()).days <= market_cap_max_age_days(source)
                )
        if "fundamental_snapshots_v3" in tables:
            fundamentals = conn.execute("SELECT COUNT(DISTINCT symbol) FROM fundamental_snapshots_v3").fetchone()[0]
    coverage = round(caps / eq * 100, 2) if eq else 0.0
    if prices < min_sessions: blockers.append("price_sessions_below_required")
    if indices < min_sessions: blockers.append("official_index_sessions_below_required")
    if eq < 1000: blockers.append("eq_security_master_incomplete")
    if coverage < min_cap_coverage: blockers.append("market_cap_coverage_below_80_percent")
    if fundamentals < max(1, int(eq * 0.5)): warnings.append("fundamentals_below_50_percent_6m_12m_promotion_limited")
    return OperationalReadiness("READY" if not blockers else "BLOCKED", prices, indices, eq, caps, coverage, fundamentals, tuple(blockers), tuple(warnings))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="nse_scanner.db")
    parser.add_argument("--output", default="output/v3_operational_readiness.json")
    parser.add_argument("--date")
    args = parser.parse_args()
    report = audit(args.db, as_of=args.date)
    payload = asdict(report)
    path = Path(args.output); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if report.status == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
