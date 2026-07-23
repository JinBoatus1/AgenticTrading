"""Shared backtesting / capital constants.

Canonical home (Phase 2C4) for backtesting constants used by backend consumers.
Moved from ``dashboard/scripts/backtest_hourly_agent.py`` and re-exported there
for backward compatibility (``bha.INITIAL_CAPITAL``).

``LLM_MODEL_NAME`` intentionally lives in
``dashboard.backend.infrastructure.llm.backtest_harness`` and is NOT duplicated
here.

Capital scale (product):
- Account portfolio equity: ``DEFAULT_PORTFOLIO_EQUITY`` ($10,000). For
  signed-in users this is a real ledger budget (unallocated cash ↔ agent
  sleeves via allocate/reclaim). Guests/demo still treat it as display-only.
- Per-agent sleeve: default ``DEFAULT_AGENT_CASH_ALLOCATION`` ($1,000),
  max ``MAX_AGENT_CASH_ALLOCATION`` ($1,000,000) — also capped by the
  account's remaining unallocated cash when the portfolio ledger is used.
- Backtests / protocol use the agent's cash allocation (falling back to
  ``INITIAL_CAPITAL``) as **simulation** capital and do not move the ledger.
"""

from __future__ import annotations

from typing import Any, Optional

# Default starting capital for a backtest when no agent allocation is set.
INITIAL_CAPITAL = 1000

# Account portfolio equity ($10k). Real ledger budget for signed-in users.
DEFAULT_PORTFOLIO_EQUITY = 10_000

# Per-agent cash allocation bounds (also enforced by the agents API).
DEFAULT_AGENT_CASH_ALLOCATION = 1000
MAX_AGENT_CASH_ALLOCATION = 1_000_000


def resolve_initial_capital(cash_allocation: Optional[Any] = None) -> float:
    """Resolve the starting capital for a backtest / protocol run.

    Uses the agent's ``cash_allocation`` when present and positive, clamped to
    ``MAX_AGENT_CASH_ALLOCATION``. Otherwise returns ``INITIAL_CAPITAL``.
    """
    if cash_allocation is None:
        return float(INITIAL_CAPITAL)
    try:
        value = float(cash_allocation)
    except (TypeError, ValueError):
        return float(INITIAL_CAPITAL)
    if value <= 0:
        return float(INITIAL_CAPITAL)
    return float(min(value, MAX_AGENT_CASH_ALLOCATION))
