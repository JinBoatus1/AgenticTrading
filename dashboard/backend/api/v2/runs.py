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

from dashboard.backend.domain.backtesting import external_run_service as ext
from dashboard.backend.api.v2.errors import ApiError
from dashboard.backend.api.v2.models import (
    DecisionRequest, RunManifest, SCHEMA_VERSION, UNIVERSE_KEY, validate_actions,
)
from dashboard.backend.api.v2.auth_scopes import require_scope
from dashboard.backend.database import db
from dashboard.backend.domain.runs.service import MAX_ACTIVE_RUNS_PER_AGENT
from dashboard.backend.execution.backtest_backend import BacktestBackend
from dashboard.backend.api.v2.rate_limit import enforce

router = APIRouter(prefix="/v2/runs", tags=["v2-runs"])

# run_id -> {"backend": ExecutionBackend, "session_id": str, "agent_id": str|None}
_runs: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()
# Serializes the cap check with run creation (check-then-act TOCTOU) — same
# pattern as the v1 protocol's _create_lock.
_create_lock = threading.Lock()

# MAX_ACTIVE_RUNS_PER_AGENT (imported from the v1 run service — one knob for
# both surfaces): each active run pins an in-memory engine session holding
# market data. NOTE: the cap is per SURFACE — v1 and v2 keep separate
# registries, so an agent can hold up to 2× the limit across both; unifying
# the registries is part of the run-lifecycle persistence work.


def _mint_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"run_{stamp}_{uuid.uuid4().hex[:8]}"


def register_run(run_id: str, backend: Any, session_id: str,
                 agent_id: Optional[str] = None) -> None:
    """Register a backend under a run_id (used by create + tests)."""
    with _lock:
        _runs[run_id] = {"backend": backend, "session_id": session_id,
                         "agent_id": agent_id}


def _active_run_count(agent_id: str) -> int:
    with _lock:
        entries = [e for e in _runs.values() if e.get("agent_id") == agent_id]
    active = 0
    for entry in entries:
        # is_active() is the passive liveness peek — never status(), which on
        # a live session can cascade into deadline handling and _finalize()
        # (seconds of baseline work) while create_run holds the global lock.
        try:
            if entry["backend"].is_active():
                active += 1
        except Exception:
            active += 1  # unknown state counts against the cap (fail closed)
    return active


def _require_run(run_id: str, session_id: str) -> Any:
    with _lock:
        entry = _runs.get(run_id)
    # A run owned by another session answers exactly like a missing one — a
    # message-text difference would let any key holder enumerate run ids.
    if not entry or entry["session_id"] != session_id:
        raise ApiError("run_not_found", f"Run {run_id} not found", status=404)
    return entry["backend"]


# -- pure helpers (unit-testable without HTTP) -----------------------------

def _context_for(run_id: str, session_id: str) -> Dict[str, Any]:
    backend = _require_run(run_id, session_id)
    return backend.build_context()


# Rejections that CONSUMED the step (the engine auto-held and advanced). These
# must replay under their idempotency key: a same-key retry that missed the
# cache would pass the step re-check and execute the stale actions against the
# NEXT step's prices. Non-consuming errors (invalid_status) change nothing
# server-side, so the same key stays retryable once the run is ready.
_STEP_CONSUMING_REJECTIONS = {"step_already_closed", "validation_failed"}


def _replay_rejection(marker: Dict[str, Any]) -> None:
    raise ApiError(
        marker["code"], marker["message"], status=marker["status"],
        details=marker.get("details"), retryable=marker.get("retryable", False),
    )


def _submit_for(run_id: str, session_id: str, idem_key: str,
                raw_actions: List[Dict[str, Any]]) -> Dict[str, Any]:
    backend = _require_run(run_id, session_id)
    step = backend.current_step_index()
    existing = db.get_idempotency(run_id, step, idem_key)
    if existing is not None:
        if isinstance(existing, dict) and "__rejection__" in existing:
            _replay_rejection(existing["__rejection__"])
        return existing
    # Partial execution (spec §5.3): drop schema-invalid actions with reasons,
    # execute the rest. If all are invalid, the step auto-holds (validation_hold).
    valid, rejected = validate_actions(raw_actions)
    try:
        ack = backend.apply_decisions(valid)
    except ApiError as exc:
        if exc.code in _STEP_CONSUMING_REJECTIONS:
            db.put_idempotency(run_id, step, idem_key, {"__rejection__": {
                "code": exc.code, "message": exc.message, "status": exc.status,
                "retryable": exc.retryable, "details": exc.details,
            }})
        raise
    if rejected:
        ack["rejected"] = list(ack.get("rejected") or []) + rejected
        if not valid:
            ack["decision_source"] = "validation_hold"
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
def create_run(body: CreateRunBody, response: Response,
               agent: dict = Depends(require_scope("runs:write"))):
    """Mint the canonical run_id, write the manifest, start the backtest load.

    ``def`` (threadpool), like every v1 protocol handler: creation touches the
    DB and the engine session synchronously (B0/H4 convention).
    """
    enforce(agent["agent_id"], response)
    with _create_lock:
        active = _active_run_count(agent["agent_id"])
        if active >= MAX_ACTIVE_RUNS_PER_AGENT:
            raise ApiError(
                "too_many_active_runs",
                f"Agent already has {active} active runs "
                f"(limit {MAX_ACTIVE_RUNS_PER_AGENT}); wait for one to finish "
                "or cancel one",
                status=429, retryable=True,
                details={"active_runs": active, "limit": MAX_ACTIVE_RUNS_PER_AGENT},
            )
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
        register_run(run_id, backend, agent["session_id"], agent["agent_id"])
    return {
        "run_id": run_id, "mode": "backtest", "status": "loading",
        "loop": backend.loop, "decision_timeout_seconds": ext.DECISION_TIMEOUT_SECONDS,
    }


@router.get("/{run_id}")
def run_status(run_id: str, agent: dict = Depends(require_scope("runs:read"))):
    backend = _require_run(run_id, agent["session_id"])
    return backend.status()


@router.get("/{run_id}/context")
def get_context(run_id: str, response: Response,
                agent: dict = Depends(require_scope("context:read"))):
    """get_context — typed context envelope for the current step."""
    enforce(agent["agent_id"], response)
    return _context_for(run_id, agent["session_id"])


@router.post("/{run_id}/decisions")
def submit_decision(run_id: str, body: DecisionRequest, response: Response,
                    agent: dict = Depends(require_scope("decisions:write"))):
    """submit_decision — idempotent per (run_id, idempotency_key); a replay
    returns the original ack even after the run has advanced to a later step.

    ``def`` (threadpool): the final step's submit runs ``_finalize()`` — two
    baseline backtests — which must never block the event loop (B0/H4).
    """
    enforce(agent["agent_id"], response)
    return _submit_for(run_id, agent["session_id"], body.idempotency_key, body.actions)


@router.get("/{run_id}/result")
def get_result(run_id: str, agent: dict = Depends(require_scope("runs:read"))):
    """get_result — metrics, equity, trades, decisions, manifest."""
    return _result_for(run_id, agent["session_id"])


@router.get("/{run_id}/decisions")
def decisions_log(run_id: str, agent: dict = Depends(require_scope("runs:read"))):
    backend = _require_run(run_id, agent["session_id"])
    return {"run_id": run_id, "decisions": backend.decisions()}


@router.post("/{run_id}/cancel")
def cancel_run(run_id: str, agent: dict = Depends(require_scope("runs:write"))):
    backend = _require_run(run_id, agent["session_id"])
    backend.cancel()
    return {"run_id": run_id, "status": "closed"}
