"""Compatibility shim.

The agent repository moved to ``dashboard.backend.domain.agents.repository``
(Phase 3A1). This module re-exports the canonical public symbols so legacy import
paths (``dashboard.backend.agent_store``) keep working unchanged. The ``AgentStore``
class and the ``agent_store`` singleton are the exact same objects as the
canonical module.
"""

from dashboard.backend.domain.agents.repository import (
    AgentStore,
    agent_store,
)

__all__ = ["AgentStore", "agent_store"]
