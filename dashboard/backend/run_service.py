"""Compatibility shim for the Run API service layer.

The implementation moved (Phase 3B1) to
``dashboard.backend.domain.runs.service``. This module re-exports the public
protocol functions and ``ProtocolRun`` so legacy imports keep working with
identical behavior. New code should import from the canonical module.
"""

from dashboard.backend.domain.runs.service import (
    ProtocolRun,
    create_run,
    get_metrics,
    get_next_step,
    get_result,
    get_step,
    list_decisions,
    list_steps,
    list_trades,
    run_status,
    run_view,
    submit_decision,
)

__all__ = [
    "ProtocolRun",
    "create_run",
    "run_view",
    "run_status",
    "get_next_step",
    "get_step",
    "submit_decision",
    "list_steps",
    "list_decisions",
    "list_trades",
    "get_metrics",
    "get_result",
]
