from pathlib import Path

from v2.candidate_diagnostics import (
    build_scanner_diagnostics,
    render_admin_diagnostics,
    save_scanner_diagnostics,
)
from v2.candidates import Candidate


def _candidate(symbol: str, classification: str, score: float, *, trigger: str = "NO_TRIGGER") -> Candidate:
    qualified = classification in {"ACTION", "WATCH"}
    return Candidate(
        symbol=symbol,
        trade_date="2026-08-04",
        horizon="POSITIONAL_3_6M",
        setup=trigger,
        selected=classification == "ACTION",
        score=score,
        reasons_for=("daily_trend",) if qualified else (),
        reasons_against=("rs63_not_positive",) if classification == "REJECT" else (),
        entry=100.0,
        stop=95.0,
        target1=107.5,
        target2=115.0,
        reward_risk_t1=1.5,
        reward_risk_t2=3.0,
        metrics={},
        classification=classification,
        primary_horizon="3M",
        eligible_horizons=("3M",) if qualified else (),
        watch_horizons=(),
        horizon_scores={
            "1M": {"state": "REJECTED", "hard_blocks": (), "component_scores": {}},
            "3M": {
                "state": "QUALIFIED" if qualified else "REJECTED",
                "hard_blocks": (),
                "component_scores": {"daily_trend": 18.0, "rs63": 16.0},
            },
            "6M": {"state": "REJECTED", "hard_blocks": (), "component_scores": {}},
            "12M": {"state": "REJECTED", "hard_blocks": (), "component_scores": {}},
        },
        entry_trigger=trigger,
        trigger_score=80.0 if trigger != "NO_TRIGGER" else 0.0,
        trade_plan_state="READY" if classification == "ACTION" else "WAIT",
        trade_plan_score=90.0 if classification == "ACTION" else 55.0,
    )


def test_build_diagnostics_counts_action_watch_and_reject():
    rows = [
        _candidate("AAA", "ACTION", 88.0, trigger="TREND_CONTINUATION"),
        _candidate("BBB", "WATCH", 82.0),
        _candidate("CCC", "REJECT", 55.0),
    ]
    report = build_scanner_diagnostics(
        rows,
        trade_date="2026-08-04",
        benchmark_source="EQUAL_WEIGHT_UNIVERSE_FALLBACK",
        benchmark_sessions=420,
    )
    assert report.universe_loaded == 3
    assert report.action_count == 1
    assert report.watch_count == 1
    assert report.reject_count == 1
    assert report.horizon_distribution["3M"] == 2
    assert report.trigger_distribution["TREND_CONTINUATION"] == 1
    assert report.rejection_reasons["rs63_not_positive"] == 1
    assert "official" in report.benchmark_reason.lower()


def test_admin_report_and_files_are_created(tmp_path: Path):
    report = build_scanner_diagnostics(
        [_candidate("AAA", "ACTION", 88.0, trigger="BREAKOUT")],
        trade_date="2026-08-04",
        benchmark_source="OFFICIAL_INDEX_HISTORY",
        benchmark_sessions=420,
    )
    message = render_admin_diagnostics(report)
    assert "MIS ADMIN DIAGNOSTICS" in message
    assert "ACTION: 1" in message

    json_path, text_path = save_scanner_diagnostics(report, tmp_path)
    assert json_path.exists()
    assert text_path.exists()
    assert '"action_count": 1' in json_path.read_text(encoding="utf-8")
    assert "ACTION: 1" in text_path.read_text(encoding="utf-8")
