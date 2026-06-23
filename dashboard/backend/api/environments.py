"""Compatibility shim for the Environment discovery router.

The implementation moved (Phase 3B3) to
``dashboard.backend.api.routers.environments``. This module re-exports the router
so legacy imports keep working with identical behavior.
"""

from dashboard.backend.api.routers.environments import router

__all__ = ["router"]
