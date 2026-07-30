"""Durable run-state manifest used for partial failure recovery."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def write_recovery_manifest(
    results: list[dict[str, Any]],
    *,
    review_period: str,
    path: str | Path = "data/portfolio_review_recovery.json",
) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    failed = [item for item in results if item.get("status") == "FAILED"]
    skipped = [item for item in results if item.get("status") == "SKIPPED"]
    payload = {
        "review_period": review_period,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "failed_symbols": [item.get("symbol", "") for item in failed],
        "skipped_symbols": [item.get("symbol", "") for item in skipped],
        "retry_required": bool(failed),
        "results": results,
    }
    destination.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return destination
