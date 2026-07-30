"""Git-persisted V2 portfolio state for disposable GitHub Actions runners."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .portfolio_store import PortfolioStore


STATE_TABLES = ("v2_positions", "v2_position_events", "v2_watchlist_memory", "v2_portfolio_snapshots")


def export_state_file(db_path: str | Path, output_path: str | Path) -> Path:
    """Write only V2 state tables, not the large reusable market-history database."""
    store = PortfolioStore(db_path)
    store.initialize()
    payload: dict[str, object] = {"schema_version": 1, "exported_at": datetime.now(timezone.utc).isoformat(), "tables": {}}
    with store.connect() as conn:
        tables = payload["tables"]
        assert isinstance(tables, dict)
        for table in STATE_TABLES:
            tables[table] = [dict(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()]
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    temporary.replace(destination)
    return destination


def restore_state_file(db_path: str | Path, input_path: str | Path) -> bool:
    """Restore the prior V2 state before a scheduled run. Missing state is valid on day one."""
    source = Path(input_path)
    if not source.exists():
        return False
    payload = json.loads(source.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or not isinstance(payload.get("tables"), dict):
        raise ValueError("unsupported V2 state file")
    store = PortfolioStore(db_path)
    store.initialize()
    with store.connect() as conn:
        conn.execute("PRAGMA foreign_keys=OFF")
        for table in reversed(STATE_TABLES):
            conn.execute(f"DELETE FROM {table}")
        for table in STATE_TABLES:
            rows = payload["tables"].get(table, [])
            if not rows:
                continue
            columns = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})")]
            usable = [column for column in columns if column in rows[0]]
            placeholders = ",".join("?" for _ in usable)
            conn.executemany(
                f"INSERT INTO {table} ({','.join(usable)}) VALUES ({placeholders})",
                [tuple(row.get(column) for column in usable) for row in rows],
            )
        conn.execute("PRAGMA foreign_keys=ON")
    return True
