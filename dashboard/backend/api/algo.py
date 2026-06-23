"""Compatibility shim for the My Trading Algo router.

The implementation moved (Phase 3C2) to ``dashboard.backend.api.routers.algo``.
This module re-exports the router and the public request models / helpers so
legacy imports keep working with identical behavior and object identity.
"""

from dashboard.backend.api.routers.algo import (
    AlgoBlocks,
    ChatRequest,
    ExecuteRequest,
    _blocks_to_dict,
    _require_session,
    router,
)

__all__ = [
    "router",
    "AlgoBlocks",
    "ChatRequest",
    "ExecuteRequest",
    "_blocks_to_dict",
    "_require_session",
]
