"""v2 runs: create · status · context · decisions · result · decisions-log · cancel.

One canonical run_id (minted here) drives the whole lifecycle (spec §4.3). Runs live
in process memory (single-worker assumption, spec §12).
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, Field

import external_backtest_service as ext
from api.v2.errors import ApiError
from api.v2.models import DecisionRequest, RunManifest, SCHEMA_VERSION, UNIVERSE_KEY
from auth_scopes import require_scope
from database import db
from execution.backtest_backend import BacktestBackend
from rate_limit import enforce

router = APIRouter(prefix="/v2/runs", tags=["v2-runs"])

# run_id -> {"backend": ExecutionBackend, "session_id": str}
_runs: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()


def _mint_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"run_{stamp}_{uuid.uuid4().hex[:8]}"


def register_run(run_id: str, backend: Any, session_id: str) -> None:
    """Register a backend under a run_id (used by create + tests)."""
    with _lock:
        _runs[run_id] = {"backend": backend, "session_id": session_id}


def _require_run(run_id: str, session_id: str) -> Any:
    with _lock:
        entry = _runs.get(run_id)
    if not entry:
        raise ApiError("run_not_found", f"Run {run_id} not found", status=404)
    if entry["session_id"] != session_id:
        raise ApiError("run_not_found", "Run not found in your session", status=404)
    return entry["backend"]


# -- pure helpers (unit-testable without HTTP) -----------------------------

def _context_for(run_id: str, session_id: str) -> Dict[str, Any]:
    backend = _require_run(run_id, session_id)
    return backend.build_context()


def _submit_for(run_id: str, session_id: str, idem_key: str,
                actions: List[Dict[str, Any]]) -> Dict[str, Any]:
    backend = _require_run(run_id, session_id)
    step = backend.current_step_index()
    existing = db.get_idempotency(run_id, step, idem_key)
    if existing is not None:
        return existing
    ack = backend.apply_decisions(actions)
    db.put_idempotency(run_id, step, idem_key, ack)
    return ack


def _result_for(run_id: str, session_id: str) -> Dict[str, Any]:
    backend = _require_run(run_id, session_id)
    res = backend.result()
    if res is None:
        raise ApiError("invalid_status", "Run not finished", status=409, retryable=True)
    return res


# -- request body ----------------------------------------------------------

class CreateRunBody(BaseModel):
    mode: str = Field(default="backtest", pattern="^backtest$")
    universe: str = Field(default=UNIVERSE_KEY, pattern="^djia_30$")
    start_date: str
    end_date: str
    agent_name: str = Field(default="external-agent", min_length=1, max_length=100)
    model_name: str = Field(default="local-model", min_length=1, max_length=100)
    strategy_mode: str = Field(default="safe_trading", pattern="^(safe_trading|buy_and_hold)$")


# -- endpoints -------------------------------------------------------------

@router.post("")
async def create_run(body: CreateRunBody, response: Response,
                     agent: dict = Depends(require_scope("runs:write"))):
    """Mint the canonical run_id, write the manifest, start the backtest load."""
    enforce(agent["agent_id"], response)
    run_id = _mint_run_id()
    backend = BacktestBackend(
        run_id=run_id, session_id=agent["session_id"], agent_name=body.agent_name,
        model_name=body.model_name, start_date=body.start_date, end_date=body.end_date,
        mode=body.strategy_mode,
    )
    manifest = RunManifest(
        agent_name=body.agent_name, model_name=body.model_name, mode="backtest",
        universe=UNIVERSE_KEY, start_date=body.start_date, end_date=body.end_date,
        decision_timeout_seconds=ext.DECISION_TIMEOUT_SECONDS,
        schema_version=SCHEMA_VERSION, news_sentiment_source=backend.news_sentiment_source,
    )
    db.insert_run_manifest(run_id, manifest.model_dump())
    backend.start_background_load()
    register_run(run_id, backend, agent["session_id"])
    return {
        "run_id": run_id, "mode": "backtest", "status": "loading",
        "loop": backend.loop, "decision_timeout_seconds": ext.DECISION_TIMEOUT_SECONDS,
    }


@router.get("/{run_id}")
async def run_status(run_id: str, agent: dict = Depends(require_scope("runs:read"))):
    backend = _require_run(run_id, agent["session_id"])
    return backend.status()


@router.get("/{run_id}/context")
async def get_context(run_id: str, response: Response,
                      agent: dict = Depends(require_scope("context:read"))):
    """get_context — typed context envelope for the current step."""
    enforce(agent["agent_id"], response)
    return _context_for(run_id, agent["session_id"])


@router.post("/{run_id}/decisions")
async def submit_decision(run_id: str, body: DecisionRequest, response: Response,
                          agent: dict = Depends(require_scope("decisions:write"))):
    """submit_decision — idempotent per (run_id, idempotency_key); a replay
    returns the original ack even after the run has advanced to a later step."""
    enforce(agent["agent_id"], response)
    actions = [a.model_dump() for a in body.actions]
    return _submit_for(run_id, agent["session_id"], body.idempotency_key, actions)


@router.get("/{run_id}/result")
async def get_result(run_id: str, agent: dict = Depends(require_scope("runs:read"))):
    """get_result — metrics, equity, trades, decisions, manifest."""
    return _result_for(run_id, agent["session_id"])


@router.get("/{run_id}/decisions")
async def decisions_log(run_id: str, agent: dict = Depends(require_scope("runs:read"))):
    backend = _require_run(run_id, agent["session_id"])
    return {"run_id": run_id, "decisions": backend.decisions()}


@router.post("/{run_id}/cancel")
async def cancel_run(run_id: str, agent: dict = Depends(require_scope("runs:write"))):
    backend = _require_run(run_id, agent["session_id"])
    backend.cancel()
    return {"run_id": run_id, "status": "closed"}
