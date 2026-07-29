"""Transparent Sprint 3 candidate scoring and horizon grouping."""
from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from .participation import evaluate_participation
from .setups import breakout_signal, compression_signal, pullback_signal
from .trade_plan import build_long_trade_plan


@dataclass(frozen=True)
class Candidate:
    symbol: str
    trade_date: str
    horizon: str
    setup: str
    selected: bool
    score: float
    reasons_for: tuple[str, ...]
    reasons_against: tuple[str, ...]
    entry: float
    stop: float
    target1: float
    target2: float
    reward_risk_t1: float
    reward_risk_t2: float
    metrics: dict[str, float]

    def to_dict(self) -> dict:
        return asdict(self)


def _horizon(frame: pd.DataFrame) -> str:
    sessions = len(frame)
    if sessions >= 260:
        return "POSITIONAL_6_12M"
    if sessions >= 120:
        return "POSITIONAL_3_6M"
    return "SWING_1_3M"


def evaluate_candidate(
    symbol: str,
    frame: pd.DataFrame,
    regime: str,
    stale_data: bool = False,
    minimum_score: float = 70.0,
) -> Candidate:
    data = frame.sort_values("trade_date").copy()
    signals = [breakout_signal(data), pullback_signal(data), compression_signal(data)]
    setup = max(signals, key=lambda signal: signal.score)
    participation = evaluate_participation(data)
    plan = build_long_trade_plan(data)

    regime_score = {"BULL": 100.0, "NEUTRAL": 55.0, "BEAR": 0.0}.get(regime.upper(), 0.0)
    score = 0.45 * setup.score + 0.25 * participation.score + 0.20 * regime_score
    score += 10.0 if plan.valid else 0.0
    score = float(max(0.0, min(100.0, score)))

    reasons_for = [reason for reason in setup.reasons if not reason.startswith("no_") and "weak" not in reason and "not_" not in reason]
    reasons_for.extend(reason for reason in participation.reasons if "confirmed" in reason)
    reasons_for.extend(reason for reason in plan.reasons if reason.endswith("_ok") or reason == "resistance_clear")
    if regime.upper() == "BULL":
        reasons_for.append("bull_market_regime")

    reasons_against = [reason for reason in setup.reasons if reason not in reasons_for]
    reasons_against.extend(reason for reason in participation.reasons if reason not in reasons_for)
    reasons_against.extend(reason for reason in plan.reasons if reason not in reasons_for)
    if regime.upper() == "BEAR":
        reasons_against.append("bear_market_hard_override")
    if stale_data:
        reasons_against.append("stale_data_hard_override")

    hard_block = stale_data or regime.upper() == "BEAR" or not plan.valid
    selected = not hard_block and setup.passed and score >= minimum_score
    metrics = dict(setup.metrics)
    metrics.update(participation.metrics)

    trade_date = pd.Timestamp(data.iloc[-1]["trade_date"]).date().isoformat() if not data.empty else ""
    return Candidate(
        symbol=symbol,
        trade_date=trade_date,
        horizon=_horizon(data),
        setup=setup.name,
        selected=selected,
        score=round(score, 2),
        reasons_for=tuple(dict.fromkeys(reasons_for)),
        reasons_against=tuple(dict.fromkeys(reasons_against)),
        entry=plan.entry,
        stop=plan.stop,
        target1=plan.target1,
        target2=plan.target2,
        reward_risk_t1=plan.reward_risk_t1,
        reward_risk_t2=plan.reward_risk_t2,
        metrics=metrics,
    )


def rank_candidates(candidates: list[Candidate], top_n: int = 10) -> dict[str, list[Candidate]]:
    selected = [candidate for candidate in candidates if candidate.selected]
    selected.sort(key=lambda candidate: (-candidate.score, candidate.symbol))
    grouped: dict[str, list[Candidate]] = {}
    for candidate in selected:
        grouped.setdefault(candidate.horizon, []).append(candidate)
    return {horizon: rows[:top_n] for horizon, rows in grouped.items()}
