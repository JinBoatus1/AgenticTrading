"""Compatibility shim for the agent-versions router.

The implementation moved (Phase 3A3) to
``dashboard.backend.api.routers.agent_versions``. This module re-exports the
router and the public symbols still referenced by callers/tests (tests patch
``agent_service``).
"""

from dashboard.backend.api.routers.agent_versions import (
    CreateVersionBody,
    agent_service,
    router,
)

__all__ = ["router", "agent_service", "CreateVersionBody"]
