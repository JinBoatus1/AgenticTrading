"""Compatibility shim for the Run API router.

The implementation moved (Phase 3B3) to ``dashboard.backend.api.routers.runs``.
This module re-exports the router and the public request models / helpers and
the repository/version-store references still referenced by callers/tests.
"""

from dashboard.backend.api.routers.runs import (
    CreateRunBody,
    EnvironmentRef,
    _handle_protocol_error,
    _require_run_owner,
    agent_version_store,
    router,
    run_service,
    run_store,
)

__all__ = [
    "router",
    "run_service",
    "run_store",
    "agent_version_store",
    "CreateRunBody",
    "EnvironmentRef",
    "_require_run_owner",
    "_handle_protocol_error",
]
