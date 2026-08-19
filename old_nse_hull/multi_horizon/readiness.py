"""Explicit, non-promoting gate for Old NSE Hull shadow graduation."""
from __future__ import annotations

import json
from pathlib import Path

from .comparison import summarize


def assess(shadow_state_path: str | Path, walkforward_path: str | Path) -> dict:
    """Return a transparent promotion decision; never changes any feature flag."""
    comparison = summarize(shadow_state_path)
    walkforward_file = Path(walkforward_path)
    walkforward = json.loads(walkforward_file.read_text(encoding="utf-8")) if walkforward_file.exists() else {}
    blockers: list[str] = []
    if not comparison["validation_ready"]:
        blockers.append(f"shadow_sessions_{comparison['sessions_observed']}_of_{comparison['target_sessions']}")
    if walkforward.get("status") != "COMPLETE" or not walkforward.get("observations"):
        blockers.append("walkforward_evidence_missing")
    return {"status": "READY_FOR_HUMAN_REVIEW" if not blockers else "BLOCKED",
            "automatic_promotion": False, "blockers": blockers,
            "comparison": comparison,
            "walkforward": {key: walkforward.get(key) for key in ("status", "observations", "samples", "mean_forward_return_pct", "median_forward_return_pct", "win_rate_pct")}}
