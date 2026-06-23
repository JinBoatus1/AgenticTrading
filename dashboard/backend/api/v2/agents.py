"""v2 agents: register / me / rotate-key (spec §4.1, §6)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field

from agent_store import agent_store
from api.v2.errors import ApiError
from auth_scopes import resolve_agent, require_scope

router = APIRouter(prefix="/v2/agents", tags=["v2-agents"])


class RegisterAgentBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    model_name: str = Field(default="local-model", max_length=100)


def _public(agent: dict) -> dict:
    return {
        "agent_id": agent["agent_id"],
        "name": agent["name"],
        "session_id": agent["session_id"],
        "model_name": agent["model_name"],
        "scopes": agent.get("scopes", []),
    }


@router.post("")
async def register(body: RegisterAgentBody, request: Request):
    """register → create an agent, return api_key (shown once), session_id, scopes."""
    browser = request.headers.get("x-session-id") or request.headers.get("X-Session-Id")
    agent = agent_store.create_agent(
        name=body.name.strip(),
        model_name=body.model_name.strip() or "local-model",
        owner_browser_session=browser.strip() if browser else None,
    )
    out = _public(agent)
    out["api_key"] = agent["api_key"]
    return out


@router.get("/me")
async def me(x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")):
    """Resolve the caller from X-API-Key → identity + scopes."""
    agent = resolve_agent(x_api_key)
    return _public(agent)


@router.post("/{agent_id}/rotate-key")
async def rotate_key(agent_id: str, agent: dict = Depends(require_scope("agents:register"))):
    """Rotate the caller's own key. The previous key stops working immediately."""
    if agent["agent_id"] != agent_id:
        raise ApiError("forbidden_scope", "Can only rotate your own key", status=403)
    new_key = agent_store.rotate_api_key(agent_id)
    if not new_key:
        raise ApiError("agent_not_found", "Agent not found", status=404)
    return {"agent_id": agent_id, "api_key": new_key}
