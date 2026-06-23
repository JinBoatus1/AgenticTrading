"""Registered external agents — persistent sessions and API keys.

Canonical location (Phase 3A3). Moved verbatim from
``dashboard/backend/api/agents.py``, which is now a thin compatibility
re-export shim. Endpoint paths, prefixes, tags, schemas, status codes,
exception messages, ownership/auth behavior, and ``AgentService`` calls are
unchanged; only the module location moved.
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from dashboard.backend.domain.agents.service import (
    AgentAccessDeniedError,
    AgentNotFoundError,
    NoExternalRunsError,
    agent_service,
)
from dashboard.backend.api.auth import _extract_bearer_token

router = APIRouter(prefix="/v1/agents", tags=["agents"])


class CreateAgentBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    model_name: str = Field(default="local-model", max_length=100)


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


@router.post("")
async def create_agent(
    body: CreateAgentBody,
    request: Request,
    authorization: Optional[str] = Header(default=None),
):
    """Register an external agent. Returns session_id and api_key (shown once)."""
    ctx = _require_owner_context(request, authorization)
    agent = agent_service.create_agent(
        name=body.name.strip(),
        model_name=body.model_name.strip() or "local-model",
        owner_user_id=ctx["user_id"],
        owner_browser_session=ctx["browser_session"],
    )
    return {
        "agent": agent_service.agent_with_stats(agent),
        "session_id": agent["session_id"],
        "api_key": agent.pop("api_key"),
        "client_hint": (
            f"python3 external_agent_client.py --api {request.base_url.scheme}://{request.base_url.netloc} "
            f"--api-key <api_key> --start 2026-04-15 --end 2026-04-16"
        ),
    }


@router.get("")
async def list_agents(
    request: Request,
    authorization: Optional[str] = Header(default=None),
):
    """List agents owned by the logged-in user and/or this browser session."""
    ctx = _owner_context(request, authorization)
    if not ctx["user_id"] and not ctx["browser_session"]:
        return {"agents": []}

    agents = agent_service.list_agents_with_stats(
        owner_user_id=ctx["user_id"],
        owner_browser_session=ctx["browser_session"],
        trading_session_id=ctx.get("trading_session"),
    )
    return {"agents": agents}


@router.post("/claim-account")
async def claim_account_agents(
    request: Request,
    authorization: Optional[str] = Header(default=None),
):
    """Link this browser's agents to the logged-in user (call after login)."""
    ctx = _owner_context(request, authorization)
    if not ctx["user_id"]:
        raise HTTPException(status_code=401, detail="Log in to claim agents")
    if not ctx["browser_session"]:
        raise HTTPException(status_code=400, detail="Missing browser session")
    claimed, agents = agent_service.claim_account_agents(
        browser_session=ctx["browser_session"],
        user_id=ctx["user_id"],
    )
    return {"claimed": claimed, "agents": agents}


class ImportSessionBody(BaseModel):
    name: Optional[str] = Field(default=None, max_length=100)
    model_name: Optional[str] = Field(default=None, max_length=100)


@router.post("/import-session")
async def import_session_agent(
    body: ImportSessionBody,
    request: Request,
    authorization: Optional[str] = Header(default=None),
):
    """Register the current trading session as an agent (for CLI runs without prior signup)."""
    ctx = _require_owner_context(request, authorization)
    session_id = ctx["browser_session"]
    try:
        agent, imported = agent_service.import_session(
            session_id=session_id,
            user_id=ctx["user_id"],
            name=body.name,
            model_name=body.model_name,
        )
    except NoExternalRunsError:
        raise HTTPException(status_code=404, detail="No external backtest runs for this session")

    result = {"agent": agent_service.agent_with_stats(agent), "imported": imported}
    if imported and agent.get("api_key"):
        result["api_key"] = agent["api_key"]
    return result


@router.get("/resolve")
async def resolve_api_key(x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")):
    """Resolve a registered agent API key to its trading session (for CLI clients)."""
    agent = agent_service.resolve_api_key(x_api_key or "")
    if not agent:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return {
        "agent_id": agent["agent_id"],
        "name": agent["name"],
        "session_id": agent["session_id"],
        "model_name": agent["model_name"],
    }


@router.get("/{agent_id}/runs")
async def list_agent_runs(
    agent_id: str,
    request: Request,
    authorization: Optional[str] = Header(default=None),
):
    """List external backtest runs for an agent."""
    ctx = _require_owner_context(request, authorization)
    agent = _require_agent_access(agent_id, ctx)
    runs = agent_service.list_external_runs(agent["session_id"])
    return {"runs": runs}


@router.get("/{agent_id}")
async def get_agent(
    agent_id: str,
    request: Request,
    authorization: Optional[str] = Header(default=None),
):
    ctx = _require_owner_context(request, authorization)
    agent = _require_agent_access(agent_id, ctx)
    return {"agent": agent_service.agent_with_stats(agent)}


@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: str,
    request: Request,
    authorization: Optional[str] = Header(default=None),
):
    ctx = _require_owner_context(request, authorization)
    _require_agent_access(agent_id, ctx)
    agent_service.delete_agent(agent_id)
    return {"status": "deleted", "agent_id": agent_id}


@router.post("/{agent_id}/rotate-api-key")
async def rotate_agent_api_key(
    agent_id: str,
    request: Request,
    authorization: Optional[str] = Header(default=None),
):
    """Generate a new API key for an agent. The previous key stops working immediately."""
    ctx = _require_owner_context(request, authorization)
    _require_agent_access(agent_id, ctx)
    api_key = agent_service.rotate_api_key(agent_id)
    if not api_key:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent = agent_service.get_agent(agent_id)
    return {
        "agent": agent_service.agent_with_stats(agent),
        "api_key": api_key,
    }


@router.post("/{agent_id}/activate")
async def activate_agent(
    agent_id: str,
    request: Request,
    authorization: Optional[str] = Header(default=None),
):
    """Return session info for switching the dashboard to this agent."""
    ctx = _require_owner_context(request, authorization)
    agent = _require_agent_access(agent_id, ctx)
    agent_service.activate_agent(
        agent_id,
        user_id=ctx.get("user_id"),
        browser_session=ctx.get("browser_session"),
    )
    return {
        "agent_id": agent["agent_id"],
        "name": agent["name"],
        "session_id": agent["session_id"],
        "model_name": agent["model_name"],
    }
