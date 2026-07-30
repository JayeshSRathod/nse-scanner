"""Generate validated monthly reviews for the prepared portfolio queue."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.portfolio_review.review_runner import run_review


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate monthly portfolio reviews")
    parser.add_argument("--queue", default="data/review_queue.json")
    parser.add_argument("--scanner", default="telegram_last_scan.json")
    parser.add_argument("--reports-root", default="reports/portfolio")
    parser.add_argument("--primary-provider", default=None)
    parser.add_argument("--fallback-provider", default=None)
    parser.add_argument("--max-symbols", type=int, default=30)
    parser.add_argument("--result", default="data/portfolio_review_run.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    queue_path = Path(args.queue)
    if not queue_path.exists():
        raise FileNotFoundError(f"Review queue not found: {queue_path}")

    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    period = str(queue.get("review_period", ""))
    items = queue.get("items", queue.get("symbols", []))
    if not isinstance(items, list):
        raise ValueError("Review queue items must be a list")

    normalized_items = []
    for item in items[: max(args.max_symbols, 0)]:
        normalized_items.append(item if isinstance(item, dict) else {"symbol": str(item), "position": {}})

    results = [
        run_review(
            item,
            period,
            scanner_path=args.scanner,
            reports_root=args.reports_root,
            primary_provider=args.primary_provider,
            fallback_provider=args.fallback_provider,
        )
        for item in normalized_items
    ]

    payload = {
        "review_period": period,
        "requested_count": len(normalized_items),
        "success_count": sum(result.status == "SUCCESS" for result in results),
        "skipped_count": sum(result.status == "SKIPPED" for result in results),
        "failed_count": sum(result.status == "FAILED" for result in results),
        "results": [asdict(result) for result in results],
    }
    output = Path(args.result)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
