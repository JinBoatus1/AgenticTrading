"""Compatibility shim for the custom-algo prompt templates.

The implementation moved (Phase 3D2) to
``dashboard.backend.infrastructure.llm.prompts``. This module re-exports the
prompt builder and risk-rule parser so legacy imports keep working with identical
behavior and object identity.
"""

from dashboard.backend.infrastructure.llm.prompts import (  # noqa: F401
    create_custom_algo_prompt,
    parse_risk_rules,
)

__all__ = ["create_custom_algo_prompt", "parse_risk_rules"]
