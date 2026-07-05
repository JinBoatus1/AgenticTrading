"""Shared backtesting constants.

Canonical home (Phase 2C4) for backtesting constants used by backend consumers.
Moved verbatim from ``dashboard/scripts/backtest_hourly_agent.py`` and re-exported
there for backward compatibility (``bha.INITIAL_CAPITAL``).

``LLM_MODEL_NAME`` intentionally lives in
``dashboard.backend.infrastructure.llm.backtest_harness`` and is NOT duplicated
here.
"""

INITIAL_CAPITAL = 100000
