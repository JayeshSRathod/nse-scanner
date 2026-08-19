"""Explicit, non-promoting gate for Old NSE Hull shadow graduation."""
from __future__ import annotations

import json
from pathlib import Path

from .comparison import summarize


def assess(shadow_state_path: str | Path, walkforward_path: str | Path, historical_state_path: str | Path | None = None) -> dict:
    """Return a transparent promotion decision; never changes any feature flag."""
    comparison = summarize(shadow_state_path)
    historical = summarize(historical_state_path) if historical_state_path else {"sessions_observed": 0, "target_sessions": 20, "validation_ready": False}
    walkforward_file = Path(walkforward_path)
    walkforward = json.loads(walkforward_file.read_text(encoding="utf-8")) if walkforward_file.exists() else {}
    blockers: list[str] = []
    if not historical["validation_ready"]:
        blockers.append(f"historical_replay_{historical['sessions_observed']}_of_{historical['target_sessions']}")
    if comparison["sessions_observed"] < 5:
        blockers.append(f"live_operational_sessions_{comparison['sessions_observed']}_of_5")
    if walkforward.get("status") != "COMPLETE" or not walkforward.get("observations"):
        blockers.append("walkforward_evidence_missing")
    return {"status": "READY_FOR_HUMAN_REVIEW" if not blockers else "BLOCKED",
            "automatic_promotion": False, "blockers": blockers,
            "comparison": comparison, "historical_replay": historical,
            "walkforward": {key: walkforward.get(key) for key in ("status", "observations", "samples", "mean_forward_return_pct", "median_forward_return_pct", "win_rate_pct")}}
