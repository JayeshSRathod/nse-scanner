import json
from pathlib import Path

from src.portfolio_review.portfolio_reader import build_review_queue, load_active_positions


def _write_portfolio(path: Path) -> None:
    payload = {
        "positions": {
            "tcs": {"status": "ACTIVE", "quantity": 10, "entry_price": 3500},
            "RELIANCE": {"status": "OPEN", "qty": 5, "entry_price": 2900},
            "EXITED": {"status": "CLOSED", "quantity": 4, "exit_date": "2026-07-01"},
            "ZEROQTY": {"status": "ACTIVE", "quantity": 0},
        },
        "closed": [],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_load_active_positions_filters_and_normalises(tmp_path: Path) -> None:
    portfolio = tmp_path / "portfolio.json"
    _write_portfolio(portfolio)

    active = load_active_positions(portfolio)

    assert set(active) == {"RELIANCE", "TCS"}


def test_build_review_queue_is_sorted_and_periodic(tmp_path: Path) -> None:
    portfolio = tmp_path / "portfolio.json"
    _write_portfolio(portfolio)

    queue = build_review_queue(portfolio, review_period="2026-08")

    assert queue["review_period"] == "2026-08"
    assert queue["count"] == 2
    assert queue["symbols"] == ["RELIANCE", "TCS"]
