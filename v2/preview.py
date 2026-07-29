"""Message 1 preview rendering for fresh V2 scanner candidates."""
from __future__ import annotations

from .candidates import Candidate


def render_candidate_preview(grouped: dict[str, list[Candidate]], regime: str, trade_date: str) -> str:
    lines = [f"NSE Scanner V2 | {trade_date}", f"Market regime: {regime}", ""]
    if not grouped:
        return "\n".join(lines + ["No fresh candidates passed all hard controls."])

    for horizon, candidates in grouped.items():
        lines.append(horizon.replace("_", " "))
        for rank, candidate in enumerate(candidates, start=1):
            lines.extend(
                [
                    f"{rank}. {candidate.symbol} | {candidate.setup} | Score {candidate.score:.1f}",
                    f"   Entry {candidate.entry:.2f} | SL {candidate.stop:.2f} | T1 {candidate.target1:.2f} | T2 {candidate.target2:.2f}",
                    f"   R:R {candidate.reward_risk_t1:.2f}/{candidate.reward_risk_t2:.2f}",
                    f"   For: {', '.join(candidate.reasons_for) or 'none'}",
                    f"   Against: {', '.join(candidate.reasons_against) or 'none'}",
                ]
            )
        lines.append("")
    return "\n".join(lines).rstrip()
