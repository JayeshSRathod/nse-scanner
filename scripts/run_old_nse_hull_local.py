"""Generate local-only Old NSE + Hull paper-validation artifacts; never sends Telegram."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from old_nse_hull.engine import render_radar, run_local, save_report


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="nse_scanner.db")
    parser.add_argument("--date")
    parser.add_argument("--output", default="output/old_nse_hull_daily.json")
    parser.add_argument("--html", default="output/old_nse_hull_daily.html")
    args = parser.parse_args()
    report = run_local(args.db, args.date)
    save_report(report, args.output)
    Path(args.html).write_text(render_radar(report), encoding="utf-8")
    print(render_radar(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
