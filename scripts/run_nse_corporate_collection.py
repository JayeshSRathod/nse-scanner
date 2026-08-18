"""Run corporate restore, collection, export and health reporting."""
from __future__ import annotations

import argparse
import json

from nse_corporate_collector import run_collection
from nse_corporate_store import export_snapshots, restore_snapshots
from v2.database import V2Database


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="nse_scanner.db")
    parser.add_argument("--date", required=True)
    parser.add_argument("--market-cap-url")
    args = parser.parse_args()
    V2Database(args.db).ensure_v3_schema()
    restored = restore_snapshots(args.db)
    health = run_collection(args.db, args.date, args.market_cap_url)
    exported = export_snapshots(args.db)
    print(json.dumps({"restored": restored, "health": health, "exported": exported}, indent=2))
    return 0 if health["status"] in {"READY", "DEGRADED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
