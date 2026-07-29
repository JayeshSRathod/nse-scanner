"""Durable backup and restore helpers for persistent V2 scanner state."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import shutil
import sqlite3

STATE_TABLES = ("v2_positions", "v2_position_events", "v2_watchlist_memory")


@dataclass(frozen=True)
class BackupResult:
    database_path: str
    backup_path: str
    manifest_path: str
    sha256: str
    table_counts: dict[str, int]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _counts(path: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    with sqlite3.connect(str(path)) as conn:
        names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in STATE_TABLES:
            counts[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) if table in names else 0
    return counts


def create_state_backup(db_path: str | Path, backup_dir: str | Path = "backups/v2") -> BackupResult:
    source = Path(db_path)
    if not source.exists():
        raise FileNotFoundError(source)
    destination_dir = Path(backup_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = destination_dir / f"v2_state_{stamp}.db"
    with sqlite3.connect(str(source)) as src, sqlite3.connect(str(backup)) as dst:
        src.backup(dst)
    with sqlite3.connect(str(backup)) as conn:
        result = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            backup.unlink(missing_ok=True)
            raise RuntimeError(f"backup integrity check failed: {result}")
    checksum = _sha256(backup)
    counts = _counts(backup)
    manifest = backup.with_suffix(".json")
    manifest.write_text(json.dumps({
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_database": str(source),
        "backup_database": str(backup),
        "sha256": checksum,
        "table_counts": counts,
    }, indent=2), encoding="utf-8")
    return BackupResult(str(source), str(backup), str(manifest), checksum, counts)


def restore_state_backup(
    backup_path: str | Path,
    db_path: str | Path,
    *,
    expected_sha256: str | None = None,
    keep_existing_copy: bool = True,
) -> Path:
    backup = Path(backup_path)
    destination = Path(db_path)
    if not backup.exists():
        raise FileNotFoundError(backup)
    actual = _sha256(backup)
    if expected_sha256 and actual != expected_sha256:
        raise ValueError("backup checksum mismatch")
    with sqlite3.connect(str(backup)) as conn:
        result = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise RuntimeError(f"backup integrity check failed: {result}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and keep_existing_copy:
        safety = destination.with_suffix(destination.suffix + ".pre_restore")
        shutil.copy2(destination, safety)
    temporary = destination.with_suffix(destination.suffix + ".restoring")
    shutil.copy2(backup, temporary)
    temporary.replace(destination)
    return destination
