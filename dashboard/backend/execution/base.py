"""ExecutionBackend interface. Schema parity is universal; lifecycle parity is per-loop."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class ExecutionBackend(ABC):
    """One run's execution. `loop` advertises lifecycle parity: lockstep | realtime."""

    loop: str = "lockstep"

    @abstractmethod
    def build_context(self) -> Dict[str, Any]:
        """Return a ContextEnvelope-shaped dict for the current step."""

    @abstractmethod
    def apply_decisions(self, actions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Validate + execute actions; return a SubmitAck-shaped dict."""

    @abstractmethod
    def status(self) -> Dict[str, Any]:
        """Return a run-status dict."""

    @abstractmethod
    def result(self) -> Optional[Dict[str, Any]]:
        """Return a ResultEnvelope-shaped dict, or None if not finalized."""

    def advance(self) -> None:
        """Lockstep stepping hook. Realtime backends are wall-clock driven (no-op)."""
        return None

    def cancel(self) -> None:
        """Best-effort cancel → closed."""
        return None
