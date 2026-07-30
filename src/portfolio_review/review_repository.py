"""Versioned JSON persistence for validated portfolio reviews."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .review_validator import assert_valid_review


class ReviewAlreadyExistsError(FileExistsError):
    """Raised when an immutable monthly review already exists."""


def save_review(
    review: dict[str, Any],
    reports_root: str | Path = "reports/portfolio",
    overwrite: bool = False,
) -> tuple[Path, Path]:
    symbol = str(review.get("symbol", "")).strip().upper()
    assert_valid_review(review, expected_symbol=symbol)

    symbol_dir = Path(reports_root) / symbol
    symbol_dir.mkdir(parents=True, exist_ok=True)
    dated_path = symbol_dir / f"{review['review_period']}.json"
    latest_path = symbol_dir / "latest.json"

    if dated_path.exists() and not overwrite:
        raise ReviewAlreadyExistsError(f"Monthly review already exists: {dated_path}")

    encoded = json.dumps(review, indent=2, ensure_ascii=False, default=str) + "\n"
    dated_path.write_text(encoded, encoding="utf-8")
    latest_path.write_text(encoded, encoding="utf-8")
    return dated_path, latest_path


def load_latest_review(symbol: str, reports_root: str | Path = "reports/portfolio") -> dict[str, Any] | None:
    path = Path(reports_root) / symbol.strip().upper() / "latest.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except (OSError, json.JSONDecodeError):
        return None
