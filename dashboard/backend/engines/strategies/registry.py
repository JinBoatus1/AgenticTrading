"""Compatibility shim — moved to domain.leaderboard.strategies.registry (Phase 3C3)."""

from dashboard.backend.domain.leaderboard.strategies.registry import (
    available_strategies,
    get_strategy,
)

__all__ = ["get_strategy", "available_strategies"]
