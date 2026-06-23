"""Compatibility shim for token usage / cost estimation.

The implementation moved (Phase 3D2) to
``dashboard.backend.infrastructure.llm.token_cost``. This module re-exports the
public API and pricing constants so legacy imports keep working with identical
behavior and object identity.
"""

from dashboard.backend.infrastructure.llm.token_cost import (  # noqa: F401
    CHARS_PER_TOKEN,
    _DEFAULT_PRICING,
    _FREE_MODEL_MARKERS,
    _PRICING_TABLE,
    estimate_cost_usd,
    estimate_tokens,
    price_for_model,
    summarize,
)

__all__ = [
    "CHARS_PER_TOKEN",
    "estimate_cost_usd",
    "estimate_tokens",
    "price_for_model",
    "summarize",
]
