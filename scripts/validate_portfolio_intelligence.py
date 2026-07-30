"""Validate Sprint 8 files and configuration without making LLM calls."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.portfolio_review.portfolio_reader import load_active_positions
from src.portfolio_review.review_validator import validate_review


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Portfolio Intelligence deployment readiness")
    parser.add_argument("--portfolio", default="portfolio.json")
    parser.add_argument("--scanner", default="telegram_last_scan.json")
    parser.add_argument("--reports-root", default="reports/portfolio")
    parser.add_argument("--strict-secrets", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    checks: list[dict[str, object]] = []

    portfolio_path = Path(args.portfolio)
    checks.append({"check": "portfolio_exists", "ok": portfolio_path.exists(), "detail": str(portfolio_path)})
    try:
        active = load_active_positions(portfolio_path) if portfolio_path.exists() else []
        checks.append({"check": "portfolio_readable", "ok": True, "detail": f"{len(active)} active positions"})
    except Exception as exc:
        checks.append({"check": "portfolio_readable", "ok": False, "detail": str(exc)})

    scanner_path = Path(args.scanner)
    checks.append({"check": "scanner_snapshot", "ok": scanner_path.exists(), "detail": str(scanner_path)})

    reports_root = Path(args.reports_root)
    invalid_reviews = 0
    review_count = 0
    if reports_root.exists():
        for latest in reports_root.glob("*/latest.json"):
            review_count += 1
            try:
                payload = json.loads(latest.read_text(encoding="utf-8"))
                if validate_review(payload, expected_symbol=latest.parent.name):
                    invalid_reviews += 1
            except Exception:
                invalid_reviews += 1
    checks.append({
        "check": "latest_reviews_valid",
        "ok": invalid_reviews == 0,
        "detail": f"{review_count} reviewed, {invalid_reviews} invalid",
    })

    configured = [name for name in ("GEMINI_API_KEY", "GROQ_API_KEY") if os.getenv(name)]
    secrets_ok = bool(configured) or not args.strict_secrets
    detail = ", ".join(configured) if configured else "No provider secret detected"
    checks.append({"check": "llm_provider_secret", "ok": secrets_ok, "detail": detail})

    required_files = [
        "data/portfolio_health.json",
        "data/portfolio_health_message.txt",
        ".github/workflows/monthly_portfolio_review.yml",
    ]
    missing = [path for path in required_files if not Path(path).exists()]
    checks.append({"check": "generated_and_workflow_files", "ok": not missing, "detail": f"missing={missing}"})

    failed = [item for item in checks if not item["ok"]]
    result = {"ready": not failed, "checks": checks, "failed_count": len(failed)}
    print(json.dumps(result, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
