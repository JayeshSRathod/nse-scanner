"""Sprint 8 command-line entry point.

The first implementation slice builds and persists the active-position review
queue. LLM, evidence and Telegram stages will be connected in later Sprint 8
sub-sprints without changing this interface.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.portfolio_review import build_review_queue


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the monthly portfolio review queue")
    parser.add_argument("--portfolio", default="portfolio.json", help="Path to portfolio JSON")
    parser.add_argument("--period", default=None, help="Review period in YYYY-MM format")
    parser.add_argument(
        "--output",
        default="data/review_queue.json",
        help="Destination for the generated review queue",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    queue = build_review_queue(args.portfolio, args.period)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(queue, indent=2, ensure_ascii=False), encoding="utf-8")

    print(
        f"Portfolio review queue created: {queue['count']} active symbols "
        f"for {queue['review_period']} -> {output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
