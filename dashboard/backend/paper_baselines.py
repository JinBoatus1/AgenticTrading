"""Compatibility shim for the paper-trading baselines module.

The implementation moved (Phase 3C5B) to
``dashboard.backend.domain.backtesting.baselines.paper``. This module re-exports
the calculator, its symbol list, and the entrypoint helper so legacy imports keep
working with identical behavior and object identity.
"""

from dashboard.backend.domain.backtesting.baselines.paper import (
    DJIA_SYMBOLS,
    PaperTradingBaselineCalculator,
    create_paper_baselines_if_not_exists,
)

__all__ = [
    "DJIA_SYMBOLS",
    "PaperTradingBaselineCalculator",
    "create_paper_baselines_if_not_exists",
]
