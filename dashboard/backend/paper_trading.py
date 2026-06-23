"""Compatibility shim for the Paper Trading module.

The provider-specific Alpaca adapter (``Position``, ``Trade``,
``AlpacaPaperTradingClient``) moved to
``dashboard.backend.infrastructure.brokers.alpaca_paper`` (Phase 3C5A), and the
session-tracking workflow (``PaperTradingSession``,
``create_paper_trading_session``) moved to
``dashboard.backend.domain.trading.paper_session`` (Phase 3C5B). This module
re-exports both so legacy imports keep working with identical behavior and
object identity.
"""

from dashboard.backend.domain.trading.paper_session import (
    PaperTradingSession,
    create_paper_trading_session,
)
from dashboard.backend.infrastructure.brokers.alpaca_paper import (
    AlpacaPaperTradingClient,
    Position,
    Trade,
)

__all__ = [
    "AlpacaPaperTradingClient",
    "Position",
    "Trade",
    "PaperTradingSession",
    "create_paper_trading_session",
]
