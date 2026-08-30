"""Send an isolated Pine Hull weekly or monthly paper-portfolio report."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pine_hull.engine import render_period_message
from pine_hull.telegram import send_period


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("period", choices=("weekly", "monthly"))
    parser.add_argument("--state-file", default="pine_hull_state.json")
    parser.add_argument("--send-telegram", action="store_true")
    args = parser.parse_args()
    message = render_period_message(args.state_file, period=args.period)
    delivery = send_period(message, period=args.period, enabled=args.send_telegram)
    print(message)
    print(f"Telegram delivery: {delivery.reason} ({delivery.message_count} message(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
