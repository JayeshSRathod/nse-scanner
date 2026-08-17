"""Read-only database access for NSE Scanner V2."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd


class V2Database:
    def __init__(self, path: str | Path = "nse_scanner.db") -> None:
        self.path = Path(path)

    def connect(self) -> sqlite3.Connection:
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        return conn

    def price_table(self, conn: sqlite3.Connection) -> str:
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "daily_prices_v2" in names:
            return "daily_prices_v2"
        if "daily_prices" in names:
            return "daily_prices"
        raise RuntimeError("No supported daily price table found")

    def load_prices(self, end_date: str | None = None, min_sessions: int = 0) -> pd.DataFrame:
        with self.connect() as conn:
            table = self.price_table(conn)
            date_col = "trade_date" if table == "daily_prices_v2" else "date"
            available = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            optional = [
                column for column in (
                    "turnover_lacs", "delivery_qty", "delivery_pct", "quality_status"
                ) if column in available
            ]
            selected = ["symbol", f"{date_col} AS trade_date", "open", "high", "low", "close", "volume", *optional]
            query = f"SELECT {', '.join(selected)} FROM {table}"
            params: list[object] = []
            if end_date:
                query += f" WHERE {date_col} <= ?"
                params.append(end_date)
            query += " ORDER BY symbol, trade_date"
            frame = pd.read_sql_query(query, conn, params=params, parse_dates=["trade_date"])
        if min_sessions:
            counts = frame.groupby("symbol")["trade_date"].nunique()
            frame = frame[frame["symbol"].isin(counts[counts >= min_sessions].index)]
        return frame

    def load_symbol_master(self) -> pd.DataFrame:
        """Return V2 symbol metadata used by the universe eligibility gate."""
        with self.connect() as conn:
            names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "symbol_master_v2" not in names:
                return pd.DataFrame(columns=["symbol", "series", "active", "market_cap_cr"])
            available = {row[1] for row in conn.execute("PRAGMA table_info(symbol_master_v2)")}
            columns = [column for column in ("symbol", "series", "active", "market_cap_cr") if column in available]
            return pd.read_sql_query(f"SELECT {', '.join(columns)} FROM symbol_master_v2", conn)

    def load_restricted_symbols(self, trade_date: str) -> dict[str, str]:
        """Load dated regulatory exclusions when a compatible table is available."""
        with self.connect() as conn:
            names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "blacklist" not in names:
                return {}
            columns = {row[1] for row in conn.execute("PRAGMA table_info(blacklist)")}
            date_column = "trade_date" if "trade_date" in columns else "date" if "date" in columns else None
            reason_column = "reason" if "reason" in columns else None
            if not date_column:
                return {}
            reason_sql = reason_column or "'REGULATORY_RESTRICTION'"
            rows = conn.execute(
                f"SELECT symbol, {reason_sql} AS reason FROM blacklist WHERE {date_column}=?",
                (trade_date,),
            ).fetchall()
            return {str(row["symbol"]): str(row["reason"] or "REGULATORY_RESTRICTION") for row in rows}

    def load_indices(self, end_date: str | None = None) -> pd.DataFrame:
        with self.connect() as conn:
            names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "index_perf" not in names:
                return pd.DataFrame(columns=["index_name", "trade_date", "open", "high", "low", "close"])
            query = "SELECT index_name, date AS trade_date, open, high, low, close FROM index_perf"
            params: list[object] = []
            if end_date:
                query += " WHERE date <= ?"
                params.append(end_date)
            query += " ORDER BY index_name, date"
            return pd.read_sql_query(query, conn, params=params, parse_dates=["trade_date"])
