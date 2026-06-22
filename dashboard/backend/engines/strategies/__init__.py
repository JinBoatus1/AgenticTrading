"""Leaderboard baseline strategies — one strategy per module.

Each strategy is independent; shared price/equity helpers live in ``_common``.
Use ``get_strategy(config)`` to resolve a strategy from a config entry.
"""

from .base import BaselineStrategy
from .registry import available_strategies, get_strategy

__all__ = ["BaselineStrategy", "get_strategy", "available_strategies"]
