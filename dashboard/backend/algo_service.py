"""Compatibility shim for the custom-algorithm backtest service.

The implementation moved (Phase 3C1) to
``dashboard.backend.domain.backtesting.algo_service``. This module re-exports the
full public API plus the module-level helpers so legacy imports keep working with
identical behavior.
"""

from dashboard.backend.domain.backtesting.algo_service import *  # noqa: F401,F403
from dashboard.backend.domain.backtesting.algo_service import (  # noqa: F401
    BLOCK_LABELS,
    CONFIG_DIR,
    DATA_DIR,
    DEFAULT_BLOCKS,
    DEFAULTS_FILE,
    LLM_MODEL,
    SUBMISSIONS_FILE,
    USER_ALGO_COLORS,
    _default_backtest_dates,
    _default_team_name,
    _has_alpaca_credentials,
    _resolve_python_exe,
    algo_status,
    execute_algo,
    get_algo_status,
    get_all_submissions,
    get_default_blocks,
    get_real_submissions,
    get_submissions_for_session,
    process_chat,
)
