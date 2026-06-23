"""Uniform error envelope for /api/v2 (spec §5.4)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import Request
from fastapi.responses import JSONResponse

ERROR_CODES = [
    "validation_failed", "step_already_closed", "run_not_found", "agent_not_found",
    "unauthorized", "forbidden_scope", "rate_limited", "universe_violation",
    "insufficient_cash", "invalid_symbol", "invalid_status",
]


class ApiError(Exception):
    """Raised anywhere in v2; rendered as {"error": {...}} by api_error_handler."""

    def __init__(self, code: str, message: str, status: int = 400,
                 details: Optional[Dict[str, Any]] = None, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details
        self.retryable = retryable

    def to_envelope(self) -> Dict[str, Any]:
        return {"error": {
            "code": self.code,
            "message": self.message,
            "details": self.details,
            "retryable": self.retryable,
        }}


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    headers = {}
    if exc.code == "rate_limited" and exc.details and "retry_after" in exc.details:
        headers["Retry-After"] = str(exc.details["retry_after"])
    return JSONResponse(status_code=exc.status, content=exc.to_envelope(), headers=headers)
