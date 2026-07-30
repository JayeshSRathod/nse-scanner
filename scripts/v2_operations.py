#!/usr/bin/env python3
"""Operational CLI for NSE Scanner V2."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from v2.health import build_health_report, write_health_report
from v2.index_ingestion import ingest_daily_index_snapshot
from v2.state_backup import create_state_backup, restore_state_backup


def main() -> int:
    parser = argparse.ArgumentParser(description="NSE Scanner V2 operations")
    parser.add_argument("--db", default="nse_scanner.db")
    sub = parser.add_subparsers(dest="command", required=True)

    index = sub.add_parser("index-update")
    index.add_argument("--date", required=True, help="Trading date YYYY-MM-DD")
    index.add_argument("--snapshot-dir", default="market_data/index_snapshots")
    index.add_argument("--csv", help="Use an already downloaded CSV instead of the network")
    index.add_argument("--url-template", default=None)

    backup = sub.add_parser("backup")
    backup.add_argument("--backup-dir", default="backups/v2")

    restore = sub.add_parser("restore")
    restore.add_argument("--backup", required=True)
    restore.add_argument("--sha256")
    restore.add_argument("--no-safety-copy", action="store_true")

    health = sub.add_parser("health")
    health.add_argument("--as-of")
    health.add_argument("--output", default="output/v2_health.json")

    args = parser.parse_args()
    if args.command == "index-update":
        content = Path(args.csv).read_bytes() if args.csv else None
        kwargs = {}
        if args.url_template:
            kwargs["url_template"] = args.url_template
        result = ingest_daily_index_snapshot(
            args.db, args.date, snapshot_dir=args.snapshot_dir,
            content=content, **kwargs,
        )
        print(json.dumps(result.__dict__, indent=2))
        return 0
    if args.command == "backup":
        result = create_state_backup(args.db, args.backup_dir)
        print(json.dumps(result.__dict__, indent=2))
        return 0
    if args.command == "restore":
        path = restore_state_backup(
            args.backup, args.db, expected_sha256=args.sha256,
            keep_existing_copy=not args.no_safety_copy,
        )
        print(json.dumps({"restored_database": str(path)}, indent=2))
        return 0
    report = build_health_report(args.db, args.as_of)
    output = write_health_report(report, args.output)
    print(json.dumps({**report.to_dict(), "output": str(output)}, indent=2))
    return 0 if report.status == "HEALTHY" else 2 if report.status == "DEGRADED" else 3


if __name__ == "__main__":
    raise SystemExit(main())
