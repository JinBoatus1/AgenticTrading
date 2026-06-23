"""Compatibility shim for the market-data quotes provider.

The implementation moved (Phase 3D1) to
``dashboard.backend.infrastructure.market_data.quotes``. This module re-exports
the public provider API and module-level cache so legacy imports keep working
with identical behavior and object identity.
"""

from dashboard.backend.infrastructure.market_data.quotes import (
    TICKER_CACHE_TTL_SECONDS,
    AlpacaMarketData,
    _extract_prev_close_from_bars,
    _extract_price_from_quote,
    _pick_first_number,
    _ticker_cache,
    _yahoo_symbol,
    get_market_quotes,
    get_yahoo_quotes_batch,
)

__all__ = [
    "TICKER_CACHE_TTL_SECONDS",
    "AlpacaMarketData",
    "get_market_quotes",
    "get_yahoo_quotes_batch",
]
