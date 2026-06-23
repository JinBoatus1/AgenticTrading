"""Compatibility shim for the external agent backtest router.

The implementation moved (Phase 3C2) to
``dashboard.backend.api.routers.external_backtest``. This module re-exports the
router and the public request models / helpers so legacy imports keep working with
identical behavior and object identity.
"""

from dashboard.backend.api.routers.external_backtest import (
    SubmitDecisionsRequest,
    StartBacktestRequest,
    TradingActionItem,
    _require_backtest,
    _require_session,
    router,
)

__all__ = [
    "router",
    "StartBacktestRequest",
    "TradingActionItem",
    "SubmitDecisionsRequest",
    "_require_session",
    "_require_backtest",
]
