"""Run the Old NSE Hull shadow comparison over retained local EOD sessions."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from old_nse_hull.discovery import load_market_data
from old_nse_hull.multi_horizon.historical_replay import run


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="nse_scanner.db")
    parser.add_argument("--sessions", type=int, default=20)
    parser.add_argument("--state", default="old_nse_hull_historical_replay_state.json")
    parser.add_argument("--output", default="output/old_nse_hull_historical_replay.json")
    args = parser.parse_args()
    report = run(load_market_data(args.db), args.db, args.state, args.sessions)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "as_of_dates"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
