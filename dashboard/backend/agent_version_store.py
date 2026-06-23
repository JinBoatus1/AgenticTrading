"""Compatibility shim.

The agent-version repository moved to
``dashboard.backend.domain.agents.version_repository`` (Phase 3A1). This module
re-exports the canonical public symbols so legacy import paths
(``dashboard.backend.agent_version_store``) keep working unchanged. The
``AgentVersionStore`` class and the ``agent_version_store`` singleton are the exact
same objects as the canonical module.
"""

from dashboard.backend.domain.agents.version_repository import (
    VALID_EXECUTION_MODES,
    VALID_VERIFICATION_LEVELS,
    AgentVersionStore,
    agent_version_store,
)

__all__ = [
    "VALID_EXECUTION_MODES",
    "VALID_VERIFICATION_LEVELS",
    "AgentVersionStore",
    "agent_version_store",
]
