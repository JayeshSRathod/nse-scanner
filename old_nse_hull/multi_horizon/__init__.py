"""Shadow-only multi-horizon upgrade for the Old NSE + Hull PAPER scanner.

This package must not be imported by the baseline discovery/Hull path except
from the opt-in shadow adapter in :mod:`old_nse_hull.engine`.
"""

from .engine import run_shadow

__all__ = ["run_shadow"]
