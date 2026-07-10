"""HTTP client helpers for the Discord bot to call ATL backend Discord APIs."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import requests

from dashboard.backend.integrations.discord_intents import (
  DEFAULT_BACKTEST_END,
  DEFAULT_BACKTEST_START,
)


def api_base() -> str:
  return os.getenv("ATL_API_BASE", "http://localhost:8000").rstrip("/")


def service_token() -> str:
  token = os.getenv("DISCORD_BOT_SERVICE_TOKEN", "").strip()
  if not token:
    token = "dev-discord-service-token"
  return token


def _headers() -> Dict[str, str]:
  return {"X-Discord-Service-Token": service_token()}


def _get(path: str, *, timeout: int = 30) -> Dict[str, Any]:
  resp = requests.get(f"{api_base()}{path}", headers=_headers(), timeout=timeout)
  resp.raise_for_status()
  return resp.json() if resp.content else {}


def _post(path: str, *, json: Dict[str, Any], timeout: int = 30) -> Dict[str, Any]:
  resp = requests.post(f"{api_base()}{path}", json=json, headers=_headers(), timeout=timeout)
  resp.raise_for_status()
  return resp.json() if resp.content else {}


def _patch(path: str, *, json: Dict[str, Any], timeout: int = 30) -> Dict[str, Any]:
  resp = requests.patch(f"{api_base()}{path}", json=json, headers=_headers(), timeout=timeout)
  resp.raise_for_status()
  return resp.json() if resp.content else {}


def get_account_link(discord_user_id: str) -> Dict[str, Any]:
  return _get(f"/api/discord/accounts/{discord_user_id}")


def create_connect_token(
  *,
  discord_user_id: str,
  discord_username: Optional[str] = None,
  guild_id: Optional[str] = None,
) -> Dict[str, Any]:
  return _post(
    "/api/discord/connect-token",
    json={
      "discord_user_id": discord_user_id,
      "discord_username": discord_username,
      "guild_id": guild_id,
    },
  )


def get_session(discord_user_id: str) -> Dict[str, Any]:
  return _get(f"/api/discord/sessions/{discord_user_id}")


def patch_session(discord_user_id: str, **fields: Any) -> Dict[str, Any]:
  return _patch(f"/api/discord/sessions/{discord_user_id}", json=fields)


def list_agents(discord_user_id: str) -> List[Dict[str, Any]]:
  data = _get(f"/api/discord/agents/{discord_user_id}")
  return data.get("agents", []) if isinstance(data, dict) else []


def create_backtest(
  *,
  discord_user_id: str,
  agent_id: str,
  symbols: List[str],
  start_date: str,
  end_date: str,
  strategy_prompt: Optional[str] = None,
) -> Dict[str, Any]:
  return _post(
    "/api/discord/backtests",
    json={
      "discord_user_id": discord_user_id,
      "agent_id": agent_id,
      "symbols": symbols,
      "start_date": start_date or DEFAULT_BACKTEST_START,
      "end_date": end_date or DEFAULT_BACKTEST_END,
      "strategy_prompt": strategy_prompt,
    },
  )


def latest_run(discord_user_id: str) -> Dict[str, Any]:
  return _get(f"/api/discord/runs/{discord_user_id}/latest")


def run_legacy_backtest(
  *,
  session_id: str,
  agent_id: str,
  start_date: str,
  end_date: str,
  strategy_prompt: Optional[str] = None,
) -> Dict[str, Any]:
  """Call the existing /backtest/run endpoint (background worker)."""
  payload: Dict[str, Any] = {
    "agent_id": agent_id,
    "start_date": start_date,
    "end_date": end_date,
  }
  if strategy_prompt:
    payload["strategy_prompt"] = strategy_prompt
  resp = requests.post(
    f"{api_base()}/backtest/run",
    json=payload,
    headers={"X-Session-Id": session_id},
    timeout=30,
  )
  resp.raise_for_status()
  return resp.json() if resp.content else {}
