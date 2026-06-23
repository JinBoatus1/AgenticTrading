"""Compatibility shim for the external agent backtest service.

The implementation moved (Phase 3C1) to
``dashboard.backend.domain.backtesting.external_run_service``. This module
re-exports the full public API plus the module-level singletons so legacy
imports keep working with identical behavior and object identity.
"""

from dashboard.backend.domain.backtesting.external_run_service import *  # noqa: F401,F403
from dashboard.backend.domain.backtesting.external_run_service import (  # noqa: F401
    DECISION_TIMEOUT_SECONDS,
    ET_TZ,
    ExternalBacktestSession,
    _iso,
    _lock,
    _sessions,
    _utcnow,
    get_backtest_decisions,
    get_current_step,
    get_decision_format,
    get_run_decisions,
    get_run_result,
    get_run_trades,
    get_session,
    get_status,
    start_backtest,
    submit_decisions,
    verify_session,
)
