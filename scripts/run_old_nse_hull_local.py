"""Generate local-only Old NSE + Hull paper-validation artifacts; never sends Telegram."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from old_nse_hull.delivery import send_radar
from old_nse_hull.engine import render_radar, run_local, save_report


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="nse_scanner.db")
    parser.add_argument("--date")
    parser.add_argument("--output", default="output/old_nse_hull_daily.json")
    parser.add_argument("--html", default="output/old_nse_hull_daily.html")
    parser.add_argument("--send-telegram", action="store_true")
    args = parser.parse_args()
    report = run_local(args.db, args.date)
    save_report(report, args.output)
    message = render_radar(report)
    Path(args.html).write_text(message, encoding="utf-8")
    print(message)
    if args.send_telegram:
        delivery = send_radar(message)
        print(f"[OLD_NSE_HULL] Telegram: {delivery.reason}")
        if not delivery.sent:
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
