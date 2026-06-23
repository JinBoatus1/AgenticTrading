"""Compatibility shim for the leaderboard contest service.

The implementation moved (Phase 3C3) to
``dashboard.backend.domain.leaderboard.service``. This module re-exports the
public API plus the patchable module globals so legacy imports keep working with
identical behavior.
"""

from dashboard.backend.domain.leaderboard.service import (  # noqa: F401
    INITIAL_CAPITAL,
    LEADERBOARD_MODE,
    _auto_compute,
    _find_cached_run,
    _rank_entries,
    _run_id,
    _symbols_for_config,
    _utcnow_iso,
    db,
    deploy_model_run,
    ensure_leaderboard_runs,
    get_leaderboard,
    get_strategy,
    load_leaderboard_config,
    token_cost,
)

__all__ = [
    "LEADERBOARD_MODE",
    "load_leaderboard_config",
    "ensure_leaderboard_runs",
    "deploy_model_run",
    "get_leaderboard",
]
