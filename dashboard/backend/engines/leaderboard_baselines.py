"""Compatibility shim for the leaderboard baseline plumbing.

The implementation moved (Phase 3C3) to
``dashboard.backend.domain.leaderboard.baselines``. This module re-exports the
public API so legacy imports keep working with identical behavior.
"""

from dashboard.backend.domain.leaderboard.baselines import (
    INITIAL_CAPITAL,
    calc_metrics,
    compute_equity_curve,
    downsample_daily,
    fetch_hourly_bars,
)

__all__ = [
    "fetch_hourly_bars",
    "compute_equity_curve",
    "calc_metrics",
    "downsample_daily",
    "INITIAL_CAPITAL",
]
