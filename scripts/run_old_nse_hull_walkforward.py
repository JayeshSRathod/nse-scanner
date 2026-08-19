"""Produce a local, read-only Old NSE Hull multi-horizon validation artifact."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from old_nse_hull.discovery import load_market_data
from old_nse_hull.multi_horizon.walkforward import run


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="nse_scanner.db")
    parser.add_argument("--output", default="output/old_nse_hull_walkforward.json")
    parser.add_argument("--sample-step", type=int, default=120)
    args = parser.parse_args()
    result = run(load_market_data(args.db), sample_step=args.sample_step)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "rows"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
