"""Compatibility shim — moved to domain.leaderboard.strategies.llm_agent (Phase 3C3).

Re-exports the strategy class plus the canonical symbols it depends on so legacy
attribute access (e.g. ``llm_agent.TechnicalIndicators``) keeps working.
"""

from dashboard.backend.domain.leaderboard.strategies.llm_agent import (
    Anthropic,
    HAS_ANTHROPIC,
    LLM_MODEL_NAME,
    LLMAgentStrategy,
    PortfolioManager,
    TechnicalIndicators,
)

__all__ = [
    "LLMAgentStrategy",
    "TechnicalIndicators",
    "PortfolioManager",
    "Anthropic",
    "HAS_ANTHROPIC",
    "LLM_MODEL_NAME",
]
