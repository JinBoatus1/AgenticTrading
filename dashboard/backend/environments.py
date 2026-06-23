"""Compatibility shim for the Agent-Environment Protocol environment registry.

The implementation moved (Phase 3B2) to
``dashboard.backend.domain.runs.environment``. This module re-exports the
registry and public functions so legacy imports keep working with identical
behavior.
"""

from dashboard.backend.domain.runs.environment import (
    ENVIRONMENTS,
    default_environment_id,
    get_environment,
    list_environments,
)

__all__ = [
    "ENVIRONMENTS",
    "list_environments",
    "get_environment",
    "default_environment_id",
]
