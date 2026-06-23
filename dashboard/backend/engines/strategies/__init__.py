"""Compatibility shim for the leaderboard baseline strategies package.

The implementation moved (Phase 3C3) to
``dashboard.backend.domain.leaderboard.strategies``. This package re-exports the
public API so legacy imports keep working with identical class identity.
"""

from dashboard.backend.domain.leaderboard.strategies import (
    BaselineStrategy,
    available_strategies,
    get_strategy,
)

__all__ = ["BaselineStrategy", "get_strategy", "available_strategies"]
