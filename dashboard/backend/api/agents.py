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
    agent = agent_store.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent_store.owns_agent(
        agent,
        owner_user_id=ctx.get("user_id"),
        owner_browser_session=ctx.get("browser_session"),
    ):
        return agent
    trading = ctx.get("trading_session")
    if trading and agent.get("session_id") == trading:
        return agent
    raise HTTPException(status_code=403, detail="Not your agent")


def _agent_with_stats(agent: Dict[str, Any]) -> Dict[str, Any]:
    runs = db.get_runs_by_session(agent["session_id"]) or []
    ext_runs = [r for r in runs if str(r.get("run_id", "")).startswith("ext_")]
    latest = None
    if ext_runs:
        latest = sorted(ext_runs, key=lambda r: r.get("created_at") or "", reverse=True)[0]
    result = dict(agent)
    result["run_count"] = len(ext_runs)
    result["latest_run"] = latest
    result["runs"] = sorted(
        ext_runs,
        key=lambda r: r.get("created_at") or "",
        reverse=True,
    )
    result["total_llm_calls"] = sum(int(r.get("llm_calls") or 0) for r in ext_runs)
    result["total_input_tokens"] = sum(int(r.get("input_tokens") or 0) for r in ext_runs)
    result["total_output_tokens"] = sum(int(r.get("output_tokens") or 0) for r in ext_runs)
    result["total_est_cost_usd"] = round(
        sum(float(r.get("est_cost_usd") or 0) for r in ext_runs), 6
    )
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
        trading_session_id=ctx.get("trading_session"),
    )
    return {"agents": [_agent_with_stats(a) for a in agents]}


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
    claimed = agent_store.claim_browser_agents_to_user(
        ctx["browser_session"],
        ctx["user_id"],
    )
    agents = agent_store.list_agents(owner_user_id=ctx["user_id"])
    return {"claimed": claimed, "agents": [_agent_with_stats(a) for a in agents]}


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
    runs = db.get_runs_by_session(session_id) or []
    ext_runs = [r for r in runs if str(r.get("run_id", "")).startswith("ext_")]
    if not ext_runs:
        raise HTTPException(status_code=404, detail="No external backtest runs for this session")

    latest = sorted(ext_runs, key=lambda r: r.get("created_at") or "", reverse=True)[0]
    name = (body.name or latest.get("agent_name") or "external-agent").strip()
    model_name = (body.model_name or latest.get("llm_model") or "local-model").strip()

    existing = agent_store.get_agent_by_session(session_id)
    if existing:
        agent = agent_store.register_or_get_agent(
            session_id=session_id,
            name=name,
            model_name=model_name,
            owner_user_id=ctx["user_id"],
            owner_browser_session=session_id,
        )
        return {"agent": _agent_with_stats(agent), "imported": False}

    agent = agent_store.register_or_get_agent(
        session_id=session_id,
        name=name,
        model_name=model_name,
        owner_user_id=ctx["user_id"],
        owner_browser_session=session_id,
    )
    result = {"agent": _agent_with_stats(agent), "imported": True}
    if agent.get("api_key"):
        result["api_key"] = agent["api_key"]
    return result


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


@router.get("/{agent_id}/runs")
async def list_agent_runs(
    agent_id: str,
    request: Request,
    authorization: Optional[str] = Header(default=None),
):
    """List external backtest runs for an agent."""
    ctx = _require_owner_context(request, authorization)
    agent = _require_agent_access(agent_id, ctx)
    runs = db.get_runs_by_session(agent["session_id"]) or []
    ext_runs = [
        r for r in runs if str(r.get("run_id", "")).startswith("ext_")
    ]
    ext_runs.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return {"runs": ext_runs}


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


@router.post("/{agent_id}/rotate-api-key")
async def rotate_agent_api_key(
    agent_id: str,
    request: Request,
    authorization: Optional[str] = Header(default=None),
):
    """Generate a new API key for an agent. The previous key stops working immediately."""
    ctx = _require_owner_context(request, authorization)
    _require_agent_access(agent_id, ctx)
    api_key = agent_store.rotate_api_key(agent_id)
    if not api_key:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent = agent_store.get_agent(agent_id)
    return {
        "agent": _agent_with_stats(agent),
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
    agent_store.claim_agent(
        agent_id,
        owner_user_id=ctx.get("user_id"),
        owner_browser_session=ctx.get("browser_session"),
    )
    return {
        "agent_id": agent["agent_id"],
        "name": agent["name"],
        "session_id": agent["session_id"],
        "model_name": agent["model_name"],
    }
