"""Discord integration API — service-token auth, account linking, DM sessions."""

from __future__ import annotations

import os
import secrets
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from dashboard.backend.api.auth import _extract_bearer_token
from dashboard.backend.domain.agents.service import AgentAccessDeniedError, agent_service
from dashboard.backend.integrations.discord_store import discord_store
from dashboard.backend.users import user_store

router = APIRouter(prefix="/discord", tags=["discord"])

WEB_BASE = os.getenv("ATL_WEB_BASE", "https://agentic-trading-lab.vercel.app").rstrip("/")
DEFAULT_BACKTEST_START = "2026-06-01"
DEFAULT_BACKTEST_END = "2026-06-30"


def _service_token() -> str:
  token = os.getenv("DISCORD_BOT_SERVICE_TOKEN", "").strip()
  if not token:
    token = "dev-discord-service-token"
  return token


def require_discord_service_token(
  x_discord_service_token: Optional[str] = Header(default=None, alias="X-Discord-Service-Token"),
) -> None:
  expected = _service_token()
  provided = (x_discord_service_token or "").strip()
  if not provided or not secrets.compare_digest(provided, expected):
    raise HTTPException(status_code=401, detail="Invalid Discord service token")


def _public_agent(agent: Dict[str, Any]) -> Dict[str, Any]:
  latest = agent.get("latest_run") or {}
  return {
    "agent_id": agent["agent_id"],
    "name": agent.get("name"),
    "model_name": agent.get("model_name") or "local-model",
    "agent_type": agent.get("agent_type") or "external",
    "description": agent.get("description"),
    "run_count": agent.get("run_count", 0),
    "latest_return": latest.get("total_return"),
    "session_id": agent.get("session_id"),
  }


def _require_linked(discord_user_id: str) -> Dict[str, Any]:
  link = discord_store.get_link(discord_user_id)
  if not link or not link.get("atl_user_id"):
    raise HTTPException(
      status_code=403,
      detail="Discord account not linked. Run /atl connect on the server.",
    )
  return link


def _verify_agent_for_user(agent_id: str, atl_user_id: int) -> Dict[str, Any]:
  try:
    return agent_service.require_access(agent_id, user_id=atl_user_id)
  except AgentAccessDeniedError:
    raise HTTPException(status_code=403, detail="Agent does not belong to this user")
  except Exception:
    raise HTTPException(status_code=404, detail="Agent not found")


class ConnectTokenBody(BaseModel):
  discord_user_id: str = Field(min_length=1, max_length=32)
  discord_username: Optional[str] = Field(default=None, max_length=100)
  guild_id: Optional[str] = Field(default=None, max_length=32)


class ConfirmLinkBody(BaseModel):
  code: str = Field(min_length=8, max_length=128)


class SessionPatchBody(BaseModel):
  selected_agent_id: Optional[str] = None
  selected_agent_version_id: Optional[str] = None
  last_run_id: Optional[str] = None
  pending_backtest: Optional[Dict[str, Any]] = None
  clear_pending: bool = False


class BacktestCreateBody(BaseModel):
  discord_user_id: str
  agent_id: str
  symbols: List[str] = Field(default_factory=list)
  start_date: str
  end_date: str
  strategy_prompt: Optional[str] = None


@router.post("/connect-token", dependencies=[Depends(require_discord_service_token)])
async def create_connect_token(body: ConnectTokenBody) -> Dict[str, Any]:
  """Bot-only: mint a one-time website link code for a Discord user."""
  result = discord_store.create_connect_token(
    discord_user_id=body.discord_user_id,
    discord_username=body.discord_username,
    guild_id=body.guild_id,
  )
  if result.get("linked"):
    return {
      "linked": True,
      "atl_user_id": result["atl_user_id"],
      "message": "Account already linked.",
    }
  code = result["code"]
  return {
    "linked": False,
    "code": code,
    "connect_url": f"{WEB_BASE}/connect-discord?code={code}",
    "expires_at": result["expires_at"],
  }


@router.post("/confirm-link")
async def confirm_link(
  body: ConfirmLinkBody,
  authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
  """Website: logged-in user confirms Discord linking with a one-time code."""
  token = _extract_bearer_token(authorization)
  if not token:
    raise HTTPException(status_code=401, detail="Log in to link Discord")
  user = user_store.get_user_for_token(token)
  if not user:
    raise HTTPException(status_code=401, detail="Invalid session")
  try:
    link = discord_store.confirm_link(link_code=body.code.strip(), atl_user_id=user["id"])
  except ValueError as exc:
    raise HTTPException(status_code=400, detail=str(exc))
  return {
    "linked": True,
    "discord_user_id": link.get("discord_user_id"),
    "atl_user_id": link.get("atl_user_id"),
  }


@router.get(
  "/accounts/{discord_user_id}",
  dependencies=[Depends(require_discord_service_token)],
)
async def get_account_link(discord_user_id: str) -> Dict[str, Any]:
  link = discord_store.get_link(discord_user_id)
  if not link:
    return {"linked": False}
  return {
    "linked": bool(link.get("atl_user_id")),
    "atl_user_id": link.get("atl_user_id"),
    "discord_username": link.get("discord_username"),
  }


@router.get(
  "/sessions/{discord_user_id}",
  dependencies=[Depends(require_discord_service_token)],
)
async def get_session(discord_user_id: str) -> Dict[str, Any]:
  link = _require_linked(discord_user_id)
  session = discord_store.get_or_create_session(
    discord_user_id=discord_user_id,
    atl_user_id=int(link["atl_user_id"]),
  )
  pending = discord_store.get_pending_backtest(discord_user_id)
  return {"session": session, "pending_backtest": pending}


@router.patch(
  "/sessions/{discord_user_id}",
  dependencies=[Depends(require_discord_service_token)],
)
async def patch_session(discord_user_id: str, body: SessionPatchBody) -> Dict[str, Any]:
  _require_linked(discord_user_id)
  session = discord_store.update_session(
    discord_user_id,
    selected_agent_id=body.selected_agent_id,
    selected_agent_version_id=body.selected_agent_version_id,
    last_run_id=body.last_run_id,
    pending_backtest=body.pending_backtest,
    clear_pending=body.clear_pending,
  )
  return {"session": session}


@router.get(
  "/agents/{discord_user_id}",
  dependencies=[Depends(require_discord_service_token)],
)
async def list_user_agents(discord_user_id: str) -> Dict[str, Any]:
  link = _require_linked(discord_user_id)
  atl_user_id = int(link["atl_user_id"])
  agents = agent_service.list_agents_with_stats(owner_user_id=atl_user_id)
  return {"agents": [_public_agent(a) for a in agents]}


@router.post(
  "/backtests",
  dependencies=[Depends(require_discord_service_token)],
)
async def create_discord_backtest(body: BacktestCreateBody) -> Dict[str, Any]:
  """Queue a backtest for a linked Discord user (interface layer — does not run inline)."""
  link = _require_linked(body.discord_user_id)
  atl_user_id = int(link["atl_user_id"])
  agent = _verify_agent_for_user(body.agent_id, atl_user_id)

  run_id = f"discord_{uuid.uuid4().hex[:12]}"
  discord_store.update_session(
    body.discord_user_id,
    last_run_id=run_id,
    clear_pending=True,
  )

  dashboard_url = f"{WEB_BASE}/app"
  return {
    "run_id": run_id,
    "status": "queued",
    "agent_id": agent["agent_id"],
    "agent_name": agent.get("name"),
    "session_id": agent.get("session_id"),
    "start_date": body.start_date,
    "end_date": body.end_date,
    "symbols": body.symbols,
    "dashboard_url": dashboard_url,
    "message": (
      "Backtest queued. Full run execution is wired through the ATL backend worker; "
      "check status with 'latest run' in DM."
    ),
  }


@router.get(
  "/runs/{discord_user_id}/latest",
  dependencies=[Depends(require_discord_service_token)],
)
async def latest_run_status(discord_user_id: str) -> Dict[str, Any]:
  link = _require_linked(discord_user_id)
  session = discord_store.get_or_create_session(
    discord_user_id=discord_user_id,
    atl_user_id=int(link["atl_user_id"]),
  )
  run_id = session.get("last_run_id")
  if not run_id:
    return {"status": "none", "message": "No backtests started yet from Discord."}

  agent_id = session.get("selected_agent_id")
  agent_name = None
  latest_metrics = None
  if agent_id:
    agent = agent_service.get_agent(agent_id)
    if agent:
      agent_name = agent.get("name")
      enriched = agent_service.agent_with_stats(agent)
      latest = enriched.get("latest_run")
      if latest:
        latest_metrics = {
          "run_id": latest.get("run_id"),
          "total_return": latest.get("total_return"),
          "start_date": latest.get("start_date"),
          "end_date": latest.get("end_date"),
          "final_equity": latest.get("final_equity"),
        }

  return {
    "run_id": run_id,
    "status": "completed" if latest_metrics else "queued",
    "agent_id": agent_id,
    "agent_name": agent_name,
    "metrics": latest_metrics,
    "dashboard_url": f"{WEB_BASE}/app",
  }
