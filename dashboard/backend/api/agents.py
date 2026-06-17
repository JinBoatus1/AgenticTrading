"""Registered external agents — persistent sessions and API keys."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from agent_store import agent_store
from api.auth import _extract_bearer_token
from database import db

router = APIRouter(prefix="/v1/agents", tags=["agents"])


class CreateAgentBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    model_name: str = Field(default="local-model", max_length=100)


def _optional_user(authorization: Optional[str]) -> Optional[dict]:
    token = _extract_bearer_token(authorization)
    if not token:
        return None
    from users import user_store

    user = user_store.get_user_for_token(token)
    return user


def _owner_context(request: Request, authorization: Optional[str]) -> Dict[str, Any]:
    browser_session = request.headers.get("x-session-id") or request.headers.get("X-Session-Id")
    user = _optional_user(authorization)
    return {
        "user_id": user["id"] if user else None,
        "browser_session": browser_session.strip() if browser_session else None,
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
    agent = agent_store.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if not agent_store.owns_agent(
        agent,
        owner_user_id=ctx.get("user_id"),
        owner_browser_session=ctx.get("browser_session"),
    ):
        raise HTTPException(status_code=403, detail="Not your agent")
    return agent


def _agent_with_stats(agent: Dict[str, Any]) -> Dict[str, Any]:
    runs = db.get_runs_by_session(agent["session_id"]) or []
    ext_runs = [r for r in runs if str(r.get("run_id", "")).startswith("ext_")]
    latest = None
    if ext_runs:
        latest = sorted(ext_runs, key=lambda r: r.get("created_at") or "", reverse=True)[0]
    result = dict(agent)
    result["run_count"] = len(ext_runs)
    result["latest_run"] = latest
    return result


@router.post("")
async def create_agent(
    body: CreateAgentBody,
    request: Request,
    authorization: Optional[str] = Header(default=None),
):
    """Register an external agent. Returns session_id and api_key (shown once)."""
    ctx = _require_owner_context(request, authorization)
    agent = agent_store.create_agent(
        name=body.name.strip(),
        model_name=body.model_name.strip() or "local-model",
        owner_user_id=ctx["user_id"],
        owner_browser_session=ctx["browser_session"],
    )
    return {
        "agent": _agent_with_stats(agent),
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

    agents = agent_store.list_agents(
        owner_user_id=ctx["user_id"],
        owner_browser_session=ctx["browser_session"],
    )
    return {"agents": [_agent_with_stats(a) for a in agents]}


@router.get("/resolve")
async def resolve_api_key(x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")):
    """Resolve a registered agent API key to its trading session (for CLI clients)."""
    agent = agent_store.resolve_api_key(x_api_key or "")
    if not agent:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return {
        "agent_id": agent["agent_id"],
        "name": agent["name"],
        "session_id": agent["session_id"],
        "model_name": agent["model_name"],
    }


@router.get("/{agent_id}")
async def get_agent(
    agent_id: str,
    request: Request,
    authorization: Optional[str] = Header(default=None),
):
    ctx = _require_owner_context(request, authorization)
    agent = _require_agent_access(agent_id, ctx)
    return {"agent": _agent_with_stats(agent)}


@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: str,
    request: Request,
    authorization: Optional[str] = Header(default=None),
):
    ctx = _require_owner_context(request, authorization)
    _require_agent_access(agent_id, ctx)
    agent_store.delete_agent(agent_id)
    return {"status": "deleted", "agent_id": agent_id}


@router.post("/{agent_id}/activate")
async def activate_agent(
    agent_id: str,
    request: Request,
    authorization: Optional[str] = Header(default=None),
):
    """Return session info for switching the dashboard to this agent."""
    ctx = _require_owner_context(request, authorization)
    agent = _require_agent_access(agent_id, ctx)
    return {
        "agent_id": agent["agent_id"],
        "name": agent["name"],
        "session_id": agent["session_id"],
        "model_name": agent["model_name"],
    }
