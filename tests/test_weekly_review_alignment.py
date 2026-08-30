from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from nse_weekly_digest import format_v3_weekly_review, get_week_dates
from pine_hull.engine import render_period_message


def test_v3_weekly_review_uses_current_plain_language() -> None:
    dates = get_week_dates(date(2026, 8, 28))
    daily = {
        "trade_date": "2026-08-27", "regime": "NEUTRAL",
        "dashboard_candidates": [{"symbol": "ABC", "score": 81, "timing_state": "READY"}],
    }
    state = {"tables": {
        "v2_positions": [{"symbol": "XYZ", "state": "OPEN", "entry": 100, "last_price": 105, "stop": 96}],
        "v2_position_events": [{"event_date": "2026-08-25", "event_type": "CREATE", "to_state": "OPEN"}],
        "v2_portfolio_snapshots": [
            {"portfolio_date": "2026-08-24", "total_pnl": 100},
            {"portfolio_date": "2026-08-27", "total_pnl": 250},
        ],
    }}
    message = format_v3_weekly_review(daily, state, dates)
    assert "NSE SCANNER V3 — WEEKLY REVIEW" in message
    assert "Watch for entry" in message
    assert "Opportunity score 81/100" in message
    assert "Price move" not in message or "PAPER POSITION OPEN" in message
    assert "BUY_TRIGGER" not in message
    assert "KAMA" not in message


def test_hull_weekly_review_is_layman_friendly(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({
        "version": 1, "last_run": "2026-08-27", "events": [],
        "positions": [{"symbol": "ABC", "state": "OPEN", "entry": 100,
                       "last_price": 104, "stop": 96, "realised_pnl": 0}],
    }), encoding="utf-8")
    message = render_period_message(state_path, period="weekly")
    assert "HULL SCANNER — WEEKLY REVIEW" in message
    assert "PAPER POSITION OPEN" in message
    assert "Price move so far: +4.00%" in message
    assert "KAMA" not in message
    assert "HTF" not in message


def test_weekly_workflows_initialize_import_paths_and_database() -> None:
    root = Path(__file__).resolve().parents[1]
    hull = (root / ".github/workflows/hull-pine-weekly.yml").read_text(encoding="utf-8")
    nse = (root / ".github/workflows/nse-weekly-digest.yml").read_text(encoding="utf-8")
    assert "PYTHONPATH: ${{ github.workspace }}" in hull
    assert "init_database(config.DB_PATH)" in nse
