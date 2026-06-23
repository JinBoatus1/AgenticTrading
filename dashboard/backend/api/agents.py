"""Compatibility shim for the registered-agents router.

The implementation moved (Phase 3A3) to
``dashboard.backend.api.routers.agents``. This module re-exports the router and
the public symbols still referenced by callers/tests (notably
``protocol_auth`` imports ``_owner_context`` / ``_require_agent_access``, and
tests patch ``agent_service``).
"""

from dashboard.backend.api.routers.agents import (
    CreateAgentBody,
    ImportSessionBody,
    _optional_user,
    _owner_context,
    _require_agent_access,
    _require_owner_context,
    agent_service,
    router,
)

__all__ = [
    "router",
    "agent_service",
    "CreateAgentBody",
    "ImportSessionBody",
    "_optional_user",
    "_owner_context",
    "_require_agent_access",
    "_require_owner_context",
]
