"""Compatibility shim for the protocol Run repository.

The implementation moved (Phase 3B1) to
``dashboard.backend.domain.runs.repository``. This module re-exports the public
class and singleton so legacy imports keep working with identical behavior.
"""

from dashboard.backend.domain.runs.repository import (
    RunStore,
    _new_run_id,
    _public_run,
    _utcnow_iso,
    run_store,
)

__all__ = ["RunStore", "run_store", "_public_run", "_new_run_id", "_utcnow_iso"]
