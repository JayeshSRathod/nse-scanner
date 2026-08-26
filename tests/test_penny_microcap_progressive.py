from __future__ import annotations

import numpy as np
import pandas as pd

from penny_microcap.engine import evaluate_symbol, scan_market
from penny_microcap.telegram import render_messages


def history(rows=300, *, last_breakout=True, circuit=False, turnover=120.0, recent_turnover=240.0):
    dates = pd.bdate_range("2025-01-01", periods=rows)
    close = np.linspace(8.0, 10.0, rows)
    close[-25:-1] = np.linspace(9.4, 9.9, 24)
    close[-1] = 10.08 if last_breakout else 9.88
    if circuit:
        close[-2] = 9.80
        close[-1] = round(close[-2] * 1.05, 2)
    frame = pd.DataFrame({"trade_date": dates, "open": close * 0.995, "high": close * 1.005,
                          "low": close * 0.99, "close": close, "volume": 1_500_000.0,
                          "turnover_lacs": turnover, "delivery_pct": 32.0})
    frame.loc[frame.index[-5:], "turnover_lacs"] = recent_turnover
    frame.loc[frame.index[-5:], "delivery_pct"] = 38.0
    if circuit:
        frame.loc[frame.index[-1], ["open", "high", "low", "close"]] = close[-1]
    return frame


META = {"series": "EQ", "active": 1, "market_cap_cr": 180.0}


def test_ready_requires_all_entry_gates():
    candidate, audit = evaluate_symbol("READY", history(), metadata=META)
    assert audit["eligible"]
    assert candidate is not None
    assert candidate.state == "READY"
    assert candidate.entry_low is not None
    assert candidate.metrics["ready_gates"]["READY_MARKET_CAP"]


def test_early_radar_does_not_require_verified_market_cap():
    frame = history(rows=140, last_breakout=False, turnover=30.0, recent_turnover=50.0)
    candidate, audit = evaluate_symbol("EARLY", frame, metadata={"series": "EQ", "active": 1})
    assert audit["eligible"]
    assert candidate is not None
    assert candidate.state == "EARLY_RADAR"
    assert not candidate.metrics["market_cap_verified"]


def test_circuit_stock_is_visible_but_never_ready():
    candidate, audit = evaluate_symbol("LOCKED", history(circuit=True), metadata=META)
    assert audit["eligible"]
    assert candidate is not None
    assert candidate.state == "CIRCUIT_LOCKED"
    assert candidate.metrics["executability"] == "UNAVAILABLE"


def test_price_below_one_is_rejected():
    frame = history(); frame[["open", "high", "low", "close"]] *= 0.05
    candidate, audit = evaluate_symbol("TOOLOW", frame, metadata=META)
    assert candidate is None
    assert audit["reason_code"] == "PRICE_OUTSIDE_PENNY_BAND"


def test_duplicate_and_stale_rows_fail_closed():
    frame = history()
    duplicated = pd.concat([frame, frame.tail(1)], ignore_index=True)
    candidate, audit = evaluate_symbol("DUP", duplicated, metadata=META)
    assert candidate is None and audit["reason_code"] == "DUPLICATE_DATES"
    candidate, audit = evaluate_symbol("STALE", frame, metadata=META,
                                       expected_as_of=frame["trade_date"].max() + pd.Timedelta(days=1))
    assert candidate is None and audit["reason_code"] == "STALE_LATEST_ROW"


def test_report_ranks_ready_before_radar_and_keeps_risk_cards():
    early = history(rows=140, last_breakout=False, turnover=30.0, recent_turnover=50.0)
    early["trade_date"] = pd.bdate_range(end=history()["trade_date"].max(), periods=len(early))
    frames = []
    for symbol, frame in [("A_READY", history()), ("B_LOCKED", history(circuit=True)),
                          ("C_EARLY", early)]:
        copy = frame.copy(); copy["symbol"] = symbol; frames.append(copy)
    master = pd.DataFrame([{"symbol": s, **META} for s in ("A_READY", "B_LOCKED")]
                          + [{"symbol": "C_EARLY", "series": "EQ", "active": 1}])
    report = scan_market(pd.concat(frames), symbol_master=master)
    assert report["candidates"][0]["state"] == "READY"
    assert report["counts"]["CIRCUIT_LOCKED"] == 1
    risk = "\n".join(render_messages(report, risk_only=True))
    assert "B_LOCKED" in risk and "NOT EXECUTABLE" in risk
    daily = "\n".join(render_messages(report))
    assert "A_READY" in daily and "C_EARLY" in daily and "B_LOCKED" not in daily
