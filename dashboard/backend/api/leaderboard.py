"""Compatibility shim for the Leaderboard router.

The implementation moved (Phase 3C4) to
``dashboard.backend.api.routers.leaderboard``. This module re-exports the router
and the service reference so legacy imports keep working with identical behavior
and object identity.
"""

from dashboard.backend.api.routers.leaderboard import get_leaderboard, router

__all__ = ["router", "get_leaderboard"]
