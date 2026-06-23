"""Shared FastAPI auth/ownership dependency helpers.

Canonical home (Phase 3A4) for the owner-context and agent-access helpers used by
both the agents router (``api/routers/agents.py``) and the protocol auth fallback
(``api/protocol_auth.py``). Moved verbatim from ``api/routers/agents.py`` so the
two consumers no longer reach through the legacy ``api/agents.py`` shim.

Authentication, ownership, browser-session fallback, exception types, and status
codes are unchanged; only the definition location moved.
"""

from typing import Any, Dict, Optional

from fastapi import HTTPException, Request

from dashboard.backend.api.auth import _extract_bearer_token
from dashboard.backend.domain.agents.service import (
    AgentAccessDeniedError,
    AgentNotFoundError,
    agent_service,
)


def _optional_user(authorization: Optional[str]) -> Optional[dict]:
    token = _extract_bearer_token(authorization)
    if not token:
        return None
    from dashboard.backend.users import user_store

    user = user_store.get_user_for_token(token)
    return user


def _owner_context(request: Request, authorization: Optional[str]) -> Dict[str, Any]:
    trading_session = request.headers.get("x-session-id") or request.headers.get("X-Session-Id")
    browser_owner = request.headers.get("x-browser-id") or request.headers.get("X-Browser-Id")
    if not browser_owner:
        browser_owner = trading_session
    user = _optional_user(authorization)
    return {
        "user_id": user["id"] if user else None,
        "browser_session": browser_owner.strip() if browser_owner else None,
        "trading_session": trading_session.strip() if trading_session else None,
    }


def _require_owner_context(request: Request, authorization: Optional[str]) -> Dict[str, Any]:
    ctx = _owner_context(request, authorization)
    if not ctx["user_id"] and not ctx["browser_session"]:
        raise HTTPException(
            status_code=400,
            detail="Missing owner context (log in or send X-Session-Id header)",
        )
    return ctx


def _require_agent_access(agent_id: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return agent_service.require_access(
            agent_id,
            user_id=ctx.get("user_id"),
            browser_session=ctx.get("browser_session"),
            trading_session=ctx.get("trading_session"),
        )
    except AgentNotFoundError:
        raise HTTPException(status_code=404, detail="Agent not found")
    except AgentAccessDeniedError:
        raise HTTPException(status_code=403, detail="Not your agent")
