"""Compatibility shim for the registered-agents router.

The implementation moved (Phase 3A3) to
``dashboard.backend.api.routers.agents``. This module re-exports the router and
the public symbols still referenced by callers/tests (tests patch
``agent_service``). The shared auth/ownership helpers moved (Phase 3A4) to
``dashboard.backend.api.dependencies`` and are no longer re-exported here.
"""

from dashboard.backend.api.routers.agents import (
    CreateAgentBody,
    ImportSessionBody,
    agent_service,
    router,
)

__all__ = [
    "router",
    "agent_service",
    "CreateAgentBody",
    "ImportSessionBody",
]
