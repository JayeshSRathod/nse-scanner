"""Institutional multi-horizon candidate evaluation and ACTION/WATCH classification."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import pandas as pd

from .entry_triggers import EntryTrigger, evaluate_entry_triggers, select_primary_trigger
from .horizon_scoring import HorizonScore, score_horizons
from .opportunity_lifecycle import compute_htf_transition, entry_horizon, entry_route, timing_state
from .pullback import PullbackResult, evaluate_pullback
from .trade_plan import TradePlan, build_trigger_trade_plan


_HORIZON_ORDER = {"1M": 1, "3M": 2, "6M": 3, "12M": 4}
FOCUS_SCORE_BY_HORIZON = {"1M": 80.0, "3M": 80.0, "6M": 82.0, "12M": 82.0}
_LEGACY_HORIZON = {
    "1M": "SWING_1_3M", "3M": "POSITIONAL_3_6M",
    "6M": "POSITIONAL_6_12M", "12M": "POSITIONAL_6_12M",
}
_ALLOWED_EARLY_BLOCKS = {"weekly_trend_not_bullish", "long_term_weekly_trend_not_bullish"}


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
    metrics: dict[str, float | bool | str]
    classification: str = "REJECT"
    primary_horizon: str = ""
    eligible_horizons: tuple[str, ...] = ()
    watch_horizons: tuple[str, ...] = ()
    horizon_scores: dict[str, dict] = field(default_factory=dict)
    entry_trigger: str = "NO_TRIGGER"
    trigger_score: float = 0.0
    trade_plan_state: str = "INVALID"
    trade_plan_score: float = 0.0
    entry_basis: str = ""
    stop_basis: str = ""
    risk_percent: float = 0.0
    valid_for_sessions: int = 0
    pullback_state: str = "NOT_EVALUATED"
    timing_state: str = "WEAK"
    htf_state: str = "NEUTRAL"
    quality_horizon: str = ""
    entry_horizon: str = ""
    entry_route: str = "DEVELOPING"

    def to_dict(self) -> dict:
        return asdict(self)


def _choose_primary_horizon(scores: dict[str, HorizonScore]) -> str:
    qualified = [row for row in scores.values() if row.state == "QUALIFIED"]
    if qualified:
        return max(qualified, key=lambda row: (row.score, _HORIZON_ORDER[row.horizon])).horizon
    watched = [row for row in scores.values() if row.state == "WATCH"]
    if watched:
        return max(watched, key=lambda row: (row.score, _HORIZON_ORDER[row.horizon])).horizon
    developing = [row for row in scores.values() if row.state == "DEVELOPING"]
    if developing:
        return max(developing, key=lambda row: (row.score, _HORIZON_ORDER[row.horizon])).horizon
    return "1M"


def focus_horizons(scores: dict[str, HorizonScore]) -> tuple[str, ...]:
    return tuple(
        horizon for horizon in ("1M", "3M", "6M", "12M")
        if scores[horizon].score >= FOCUS_SCORE_BY_HORIZON[horizon] and not scores[horizon].hard_blocks
    )


def _classification(scores: dict[str, HorizonScore], trigger: EntryTrigger, plan: TradePlan, *, stale_data: bool) -> str:
    if stale_data:
        return "REJECT"
    focused = focus_horizons(scores)
    if focused and trigger.actionable and plan.state == "READY":
        return "ACTION"
    if focused:
        return "WATCH"
    return "REJECT"


def _can_surface_early(primary: HorizonScore, metrics: dict[str, float | bool | str], htf_state: str, *, stale_data: bool, regime: str) -> bool:
    """Allow a developing HTF transition into WATCH, never directly into ACTION."""
    blocks = set(primary.hard_blocks)
    return bool(
        not stale_data
        and regime.upper() not in {"BEAR", "BEARISH"}
        and primary.score >= 70.0
        and bool(metrics.get("daily_bullish"))
        and bool(metrics.get("kama_rising"))
        and htf_state in {"BULLISH", "IMPROVING", "NEUTRAL"}
        and blocks.issubset(_ALLOWED_EARLY_BLOCKS)
    )


def evaluate_candidate(
    symbol: str,
    frame: pd.DataFrame,
    regime: str,
    stale_data: bool = False,
    minimum_score: float = 70.0,
    benchmark_close: pd.Series | None = None,
) -> Candidate:
    del minimum_score
    data = frame.sort_values("trade_date").copy()
    trade_date = pd.Timestamp(data.iloc[-1]["trade_date"]).date().isoformat() if not data.empty else ""
    horizons = score_horizons(data, regime, benchmark_close=benchmark_close)
    primary_horizon = _choose_primary_horizon(horizons)
    pullback: PullbackResult = evaluate_pullback(data, horizons)
    triggers = evaluate_entry_triggers(data, horizons, pullback)
    primary_trigger = select_primary_trigger(triggers)
    plan = build_trigger_trade_plan(data, primary_trigger, primary_horizon)

    metrics: dict[str, float | bool | str] = dict(horizons[primary_horizon].metrics)
    metrics.update(primary_trigger.metrics)
    htf_state, htf_metrics = compute_htf_transition(data)
    metrics.update(htf_metrics)

    classification = _classification(horizons, primary_trigger, plan, stale_data=stale_data)
    if classification == "REJECT" and _can_surface_early(horizons[primary_horizon], metrics, htf_state, stale_data=stale_data, regime=regime):
        classification = "WATCH"

    eligible = tuple(h for h in ("1M", "3M", "6M", "12M") if horizons[h].state == "QUALIFIED")
    watched = tuple(h for h in ("1M", "3M", "6M", "12M") if horizons[h].state == "WATCH")
    focused = focus_horizons(horizons)
    research = tuple(h for h in ("1M", "3M", "6M", "12M") if horizons[h].state in {"QUALIFIED", "WATCH"})
    primary_score = float(horizons[primary_horizon].score)

    reasons_for: list[str] = list(horizons[primary_horizon].reasons_for)
    if primary_trigger.actionable:
        reasons_for.extend(primary_trigger.reasons)
    reasons_for.extend(reason for reason in plan.reasons if reason.endswith("_ok") or reason == "resistance_clear")
    if classification == "WATCH" and htf_state == "IMPROVING":
        reasons_for.append("higher_timeframe_improving")

    reasons_against: list[str] = list(horizons[primary_horizon].reasons_against)
    if regime.upper() in {"BEAR", "BEARISH"}:
        reasons_against.append("bear_market_hard_override")
    if stale_data:
        reasons_against.append("stale_data_hard_override")
    if not primary_trigger.actionable:
        reasons_against.append("no_actionable_entry_trigger")
    if plan.state != "READY":
        reasons_against.extend(plan.reasons)

    execution_horizon = entry_horizon(primary_horizon, primary_trigger.name)
    route = entry_route(primary_trigger.name, pullback.state, classification)
    opportunity_state = timing_state(
        classification=classification, metrics=metrics, htf_state=htf_state,
        trade_plan_state=plan.state, reward_risk_t1=plan.reward_risk_t1, pullback_state=pullback.state,
    )
    metrics.update({
        "classification": classification, "primary_horizon": primary_horizon,
        "quality_horizon": primary_horizon, "entry_horizon": execution_horizon,
        "entry_route": route, "timing_state": opportunity_state, "htf_state": htf_state,
        "eligible_horizons": ",".join(eligible), "watch_horizons": ",".join(watched),
        "focus_horizons": ",".join(focused), "research_horizons": ",".join(research),
        "trade_plan_state": plan.state, "trade_plan_score": plan.score, "pullback_state": pullback.state,
    })

    return Candidate(
        symbol=symbol, trade_date=trade_date, horizon=_LEGACY_HORIZON[primary_horizon], setup=primary_trigger.name,
        selected=classification == "ACTION", score=round(primary_score, 2),
        reasons_for=tuple(dict.fromkeys(reasons_for)), reasons_against=tuple(dict.fromkeys(reasons_against)),
        entry=plan.entry, stop=plan.stop, target1=plan.target1, target2=plan.target2,
        reward_risk_t1=plan.reward_risk_t1, reward_risk_t2=plan.reward_risk_t2, metrics=metrics,
        classification=classification, primary_horizon=primary_horizon, eligible_horizons=eligible,
        watch_horizons=watched, horizon_scores={h: row.to_dict() for h, row in horizons.items()},
        entry_trigger=primary_trigger.name, trigger_score=round(primary_trigger.score, 2),
        trade_plan_state=plan.state, trade_plan_score=plan.score, entry_basis=plan.entry_basis,
        stop_basis=plan.stop_basis, risk_percent=plan.risk_percent, valid_for_sessions=plan.valid_for_sessions,
        pullback_state=pullback.state, timing_state=opportunity_state, htf_state=htf_state,
        quality_horizon=primary_horizon, entry_horizon=execution_horizon, entry_route=route,
    )


def rank_candidates(candidates: list[Candidate], top_n: int | None = 10) -> dict[str, list[Candidate]]:
    selected = [candidate for candidate in candidates if candidate.classification == "ACTION"]
    selected.sort(key=lambda candidate: (-candidate.score, -candidate.trade_plan_score, candidate.symbol))
    grouped: dict[str, list[Candidate]] = {}
    for candidate in selected:
        grouped.setdefault(candidate.horizon, []).append(candidate)
    if top_n is None:
        return grouped
    return {horizon: rows[:top_n] for horizon, rows in grouped.items()}


def watch_candidates(candidates: list[Candidate]) -> list[Candidate]:
    rows = [candidate for candidate in candidates if candidate.classification == "WATCH"]
    return sorted(rows, key=lambda candidate: (-candidate.score, candidate.symbol))
