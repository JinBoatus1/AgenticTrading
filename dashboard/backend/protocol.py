"""Compatibility shim for the Agent-Environment Protocol primitives.

The implementation moved (Phase 3B2) to
``dashboard.backend.domain.runs.protocol``. This module re-exports the public
classes, constants, and helpers so legacy imports keep working with identical
behavior.
"""

from dashboard.backend.domain.runs.protocol import (
    PROTOCOL_VERSION,
    VALID_ORDER_TYPES,
    VALID_QUANTITY_TYPES,
    VALID_SIDES,
    DecisionIn,
    OrderIn,
    ProtocolError,
    error_body,
    order_to_action,
    resolve_order_quantity,
)

__all__ = [
    "PROTOCOL_VERSION",
    "VALID_SIDES",
    "VALID_QUANTITY_TYPES",
    "VALID_ORDER_TYPES",
    "ProtocolError",
    "error_body",
    "OrderIn",
    "DecisionIn",
    "resolve_order_quantity",
    "order_to_action",
]
