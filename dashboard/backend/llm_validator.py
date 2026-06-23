"""Compatibility shim for the LLM trading-decision validator.

The implementation moved (Phase 3D2) to
``dashboard.backend.infrastructure.llm.validator``. This module re-exports the
public API, constants, prompt templates, and helpers so legacy imports keep
working with identical behavior and object identity.
"""

from dashboard.backend.infrastructure.llm.validator import (  # noqa: F401
    BUY_AND_HOLD_PROMPT,
    DJIA_30,
    LLMTradingDecision,
    LLMTradingDecisionBatch,
    PortfolioConstraints,
    SAFE_TRADING_PROMPT,
    TOP_10_STOCKS,
    TradingAction,
    actions_to_executable,
    create_prompt,
    create_safe_prompt,
    log_audit_trail,
    parse_actions_payload,
    validate_llm_response,
)

__all__ = [
    "BUY_AND_HOLD_PROMPT",
    "DJIA_30",
    "LLMTradingDecision",
    "LLMTradingDecisionBatch",
    "PortfolioConstraints",
    "SAFE_TRADING_PROMPT",
    "TOP_10_STOCKS",
    "TradingAction",
    "actions_to_executable",
    "create_prompt",
    "create_safe_prompt",
    "log_audit_trail",
    "parse_actions_payload",
    "validate_llm_response",
]
