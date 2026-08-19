"""Send the independent Old NSE + Hull PAPER weekly or monthly topic report."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from old_nse_hull.delivery import send_period
from old_nse_hull.engine import render_period_report, run_local
from old_nse_hull.multi_horizon.comparison import summarize


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("period", choices=("weekly", "monthly"))
    parser.add_argument("--db", default="nse_scanner.db")
    parser.add_argument("--shadow-state", default="old_nse_hull_shadow_state.json")
    parser.add_argument("--send-telegram", action="store_true")
    args = parser.parse_args()
    message = render_period_report(run_local(args.db), args.period, summarize(args.shadow_state))
    print(message)
    if args.send_telegram and not send_period(message, args.period).sent:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
