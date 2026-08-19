"""Report whether the multi-horizon shadow can be presented for human promotion review."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from old_nse_hull.multi_horizon.readiness import assess


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shadow-state", default="old_nse_hull_shadow_state.json")
    parser.add_argument("--walkforward", default="output/old_nse_hull_walkforward.json")
    parser.add_argument("--historical-state", default="old_nse_hull_historical_replay_state.json")
    args = parser.parse_args()
    result = assess(args.shadow_state, args.walkforward, args.historical_state)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "READY_FOR_HUMAN_REVIEW" else 2


if __name__ == "__main__":
    raise SystemExit(main())
