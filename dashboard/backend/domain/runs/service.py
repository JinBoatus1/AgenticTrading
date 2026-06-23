"""Agent-Environment Protocol orchestration (Run API service layer).

This is a thin adapter over the existing external backtest engine
(``external_backtest_service``). It exposes the generalized Run/Step/Decision/
ExecutionResult protocol while delegating all data loading, validation,
execution and persistence to the engine and ``llm_validator``. It adds:

* stable, immutable step IDs over the engine's single mutable "current step",
* idempotency keys and per-step finalization guards,
* protocol-shaped Observation / ExecutionResult payloads,
* a simple run/step state machine and clear deadline errors.

Moved verbatim (Phase 3B1) from ``dashboard/backend/run_service.py``, which is
now a thin compatibility re-export shim. Public functions, ``ProtocolRun``,
module-level registries, signatures, and behavior are unchanged; only the module
location moved (and the ``run_store`` import now points at the canonical
repository).
"""

from __future__ import annotations

import threading
import uuid
from typing import Any, Dict, List, Optional

import dashboard.backend.domain.backtesting.external_run_service as ebs
from dashboard.backend.database import db
from dashboard.backend.domain.runs.environment import get_environment
from dashboard.backend.llm_validator import DJIA_30
from dashboard.backend.domain.runs.protocol import (
    PROTOCOL_VERSION,
    VALID_SIDES,
    DecisionIn,
    ProtocolError,
    order_to_action,
    resolve_order_quantity,
)
from dashboard.backend.domain.runs.repository import run_store

_runs: Dict[str, "ProtocolRun"] = {}
_registry_lock = threading.Lock()

# Engine status -> protocol run status
_RUN_STATUS_MAP = {
    "loading": "running",
    "waiting_decision": "running",
    "completed": "completed",
    "failed": "failed",
}


def _new_decision_id() -> str:
    return f"dec_{uuid.uuid4().hex[:12]}"


def _new_step_id() -> str:
    return f"step_{uuid.uuid4().hex[:12]}"


class ProtocolRun:
    """In-memory protocol state for one run, layered on an engine session."""

    def __init__(self, *, record: Dict[str, Any], environment: Dict[str, Any]):
        self.run_id: str = record["run_id"]
        self.backtest_id: Optional[str] = record.get("backtest_id")
        self.session_id: str = record["session_id"]
        self.config: Dict[str, Any] = record.get("config") or {}
        self.environment = environment
        self.result_run_id: Optional[str] = record.get("result_run_id")
        self.status: str = record.get("status") or "running"

        self.lock = threading.Lock()
        self.seq_to_step_id: Dict[int, str] = {}
        self.step_seq: Dict[str, int] = {}
        self.step_meta: Dict[str, Dict[str, Any]] = {}
        # idempotency_key -> stored ExecutionResult
        self.idempotency: Dict[str, Dict[str, Any]] = {}
        # sequence -> {"idempotency_key", "result"}
        self.step_results_by_seq: Dict[int, Dict[str, Any]] = {}

    def session(self):
        if not self.backtest_id:
            return None
        return ebs.get_session(self.backtest_id)

    def ensure_step_id(self, seq: int, timestamp: Any, deadline: Any) -> str:
        sid = self.seq_to_step_id.get(seq)
        if sid is None:
            sid = _new_step_id()
            self.seq_to_step_id[seq] = sid
            self.step_seq[sid] = seq
            self.step_meta[sid] = {
                "sequence": seq,
                "timestamp": timestamp,
                "deadline_at": deadline,
                "status": "awaiting_decision",
            }
        else:
            self.step_meta[sid].update(
                {"timestamp": timestamp, "deadline_at": deadline, "status": "awaiting_decision"}
            )
        return sid

    def constraints(self) -> Dict[str, Any]:
        env_constraints = self.environment.get("constraints", {})
        symbols = self.config.get("symbols") or self.environment.get("universe")
        return {
            "allowed_symbols": symbols,
            "allow_short": bool(env_constraints.get("allow_short", False)),
            "max_position_weight": env_constraints.get("max_position_weight", 0.25),
            "max_orders": env_constraints.get("max_orders", 10),
        }


def _get_run(run_id: str) -> "ProtocolRun":
    with _registry_lock:
        run = _runs.get(run_id)
    if run is None:
        # Allow read-only access to a finalized run after the in-memory
        # session is gone (e.g. metrics/result fetched later).
        record = run_store.get_run(run_id)
        if record is None:
            raise ProtocolError("run_not_found", "Run not found", status_code=404)
        env = get_environment(record.get("environment_id")) or {}
        run = ProtocolRun(record=record, environment=env)
        with _registry_lock:
            _runs[run_id] = run
    return run


def _sync_status(run: "ProtocolRun") -> Dict[str, Any]:
    """Reconcile engine status into the protocol run; persist completion."""
    session = run.session()
    if session is None:
        return {"engine_status": None, "run_status": run.status}

    engine_status = session.get_status()  # applies timeout side-effects
    estatus = engine_status.get("status")
    run.status = _RUN_STATUS_MAP.get(estatus, run.status)

    if estatus == "completed" and not run.result_run_id and session.run_id:
        run.result_run_id = session.run_id
        run_store.update_run(
            run.run_id,
            result_run_id=session.run_id,
            status="completed",
        )
    elif estatus == "failed":
        run_store.update_run(run.run_id, status="failed")
    return {"engine_status": engine_status, "run_status": run.status}


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------


def create_run(
    *,
    agent: Dict[str, Any],
    agent_version: Dict[str, Any],
    environment_id: str,
    config: Dict[str, Any],
) -> Dict[str, Any]:
    environment = get_environment(environment_id)
    if environment is None:
        raise ProtocolError("unknown_environment", f"Unknown environment '{environment_id}'", 404)
    if environment.get("type") != "backtest":
        raise ProtocolError(
            "unsupported_environment",
            "Only backtest environments are supported in this version",
            400,
        )

    start_date = config.get("start_date")
    end_date = config.get("end_date")
    if not start_date or not end_date:
        raise ProtocolError("invalid_config", "config.start_date and config.end_date are required", 400)

    symbols = config.get("symbols")
    if symbols:
        invalid = [s for s in symbols if s not in DJIA_30]
        if invalid:
            raise ProtocolError(
                "invalid_symbols",
                f"Symbols not in environment universe: {invalid}",
                400,
                details={"invalid_symbols": invalid},
            )

    mode = config.get("mode", "safe_trading")
    if mode not in ("safe_trading", "buy_and_hold"):
        raise ProtocolError("invalid_config", f"Unsupported mode '{mode}'", 400)

    start_res = ebs.start_backtest(
        session_id=agent["session_id"],
        agent_name=agent.get("name") or "external-agent",
        model_name=agent.get("model_name") or "local-model",
        start_date=start_date,
        end_date=end_date,
        mode=mode,
    )
    backtest_id = start_res["backtest_id"]

    record = run_store.create_run(
        agent_id=agent.get("agent_id"),
        agent_version_id=agent_version.get("agent_version_id") if agent_version else None,
        session_id=agent["session_id"],
        environment_id=environment_id,
        environment_type=environment.get("type"),
        config=config,
        backtest_id=backtest_id,
        status="running",
    )

    run = ProtocolRun(record=record, environment=environment)
    with _registry_lock:
        _runs[run.run_id] = run

    return run_view(run.run_id)


def run_view(run_id: str) -> Dict[str, Any]:
    run = _get_run(run_id)
    status = _sync_status(run)
    session = run.session()
    record = run_store.get_run(run_id) or {}
    view = {
        "protocol_version": PROTOCOL_VERSION,
        "run_id": run.run_id,
        "agent_id": record.get("agent_id"),
        "agent_version_id": record.get("agent_version_id"),
        "environment": {
            "environment_id": record.get("environment_id"),
            "type": record.get("environment_type"),
        },
        "config": run.config,
        "status": run.status,
        "result_run_id": run.result_run_id,
        "created_at": record.get("created_at"),
    }
    if session is not None:
        engine = status["engine_status"] or {}
        view["progress"] = {
            "step_index": engine.get("step_index"),
            "total_steps": engine.get("total_steps"),
        }
        if engine.get("metrics"):
            view["metrics"] = engine["metrics"]
        if engine.get("compare_url"):
            view["compare_url"] = engine["compare_url"]
    return view


def run_status(run_id: str) -> Dict[str, Any]:
    run = _get_run(run_id)
    status = _sync_status(run)
    engine = status["engine_status"] or {}
    return {
        "protocol_version": PROTOCOL_VERSION,
        "run_id": run.run_id,
        "status": run.status,
        "step_index": engine.get("step_index"),
        "total_steps": engine.get("total_steps"),
        "result_run_id": run.result_run_id,
    }


def get_next_step(run_id: str) -> Dict[str, Any]:
    run = _get_run(run_id)
    session = run.session()
    if session is None:
        raise ProtocolError("run_not_active", "Run session is no longer active", 409)

    step = session.get_current_step()
    estatus = step.get("status")

    if estatus == "loading":
        return {
            "protocol_version": PROTOCOL_VERSION,
            "run_id": run.run_id,
            "status": "loading",
            "message": step.get("message", "Loading market data..."),
        }
    if estatus == "failed":
        raise ProtocolError("run_failed", step.get("error") or "Run failed", 500)
    if estatus == "completed":
        _sync_status(run)
        return {
            "protocol_version": PROTOCOL_VERSION,
            "run_id": run.run_id,
            "status": "completed",
            "result_run_id": run.result_run_id,
            "message": "Run completed; no further steps.",
        }

    seq = step["step_index"]
    timestamp = step["timestamp"]
    deadline = step.get("decision_deadline_at")
    step_id = run.ensure_step_id(seq, timestamp, deadline)
    return _build_step_view(run, session, seq, step_id, step)


def get_step(run_id: str, step_id: str) -> Dict[str, Any]:
    run = _get_run(run_id)
    seq = run.step_seq.get(step_id)
    if seq is None:
        raise ProtocolError("unknown_step", "Unknown step_id for this run", 404)

    session = run.session()
    if session is not None:
        # Trigger any pending timeout, then classify.
        session.get_status()
        if session.status == "waiting_decision" and session.step_index == seq:
            step = session.get_current_step()
            if step.get("status") == "waiting_decision":
                return _build_step_view(run, session, seq, step_id, step)

    meta = run.step_meta.get(step_id, {})
    status = _historical_step_status(run, seq)
    return {
        "protocol_version": PROTOCOL_VERSION,
        "run_id": run.run_id,
        "step_id": step_id,
        "sequence": seq,
        "timestamp": _iso(meta.get("timestamp")),
        "deadline_at": meta.get("deadline_at"),
        "status": status,
    }


def submit_decision(run_id: str, step_id: str, decision: DecisionIn) -> Dict[str, Any]:
    run = _get_run(run_id)
    with run.lock:
        # Idempotent replay
        if decision.idempotency_key in run.idempotency:
            return run.idempotency[decision.idempotency_key]

        session = run.session()
        if session is None:
            raise ProtocolError("run_not_active", "Run session is no longer active", 409)

        session.get_status()  # apply timeout side effects
        seq = run.step_seq.get(step_id)
        if seq is None:
            raise ProtocolError("unknown_step", "Unknown step_id for this run", 404)

        current_index = session.step_index
        if session.status == "completed" or seq < current_index:
            prior = run.step_results_by_seq.get(seq)
            if prior and prior["idempotency_key"] == decision.idempotency_key:
                return prior["result"]
            raise ProtocolError(
                "step_already_finalized",
                "This step already has a finalized decision",
                409,
            )
        if seq > current_index:
            raise ProtocolError("step_not_active", "Step is not the active step", 409)

        # seq == current active step
        timestamp = session.timestamps[current_index]
        prices = session.protocol_current_prices(timestamp)
        portfolio_before = session.protocol_portfolio(timestamp)
        equity_before = portfolio_before["equity"]
        cash_before = float(session.manager.cash)
        positions_before = dict(session.manager.positions)

        accepted_actions: List[Dict[str, Any]] = []
        rejections: List[Dict[str, Any]] = []
        confidence = decision.confidence if decision.confidence is not None else 0.75

        for order in decision.orders:
            side = order.side.lower()
            order_repr = order.model_dump()
            if side not in VALID_SIDES:
                rejections.append({"order": order_repr, "reason": "invalid_side"})
                continue
            if order.symbol not in DJIA_30:
                rejections.append({"order": order_repr, "reason": "invalid_symbol"})
                continue
            shares, qerr = resolve_order_quantity(
                order, price=prices.get(order.symbol, 0), equity=equity_before
            )
            if qerr:
                rejections.append({"order": order_repr, "reason": qerr})
                continue
            if shares <= 0:
                rejections.append({"order": order_repr, "reason": "zero_quantity"})
                continue
            accepted_actions.append(
                order_to_action(
                    order, shares=shares, confidence=confidence, rationale=decision.rationale
                )
            )

        trades_before = session.trade_count()
        engine_result = session.submit_decisions({"actions": accepted_actions})

        if not engine_result.get("accepted"):
            err = engine_result.get("error", "")
            if err == "step_already_closed":
                raise ProtocolError(
                    "decision_deadline_exceeded",
                    "Decision arrived after the step deadline; step auto-held",
                    409,
                    details={"outcome": engine_result.get("outcome")},
                )
            if err == "backtest_already_completed":
                raise ProtocolError("run_completed", "Run already completed", 409)
            # validation_hold / invalid_status: treat all submitted orders as rejected
            for action in accepted_actions:
                rejections.append({"order": action, "reason": err or "validation_failed"})
            accepted_actions = []
            executed = []
        else:
            executed = engine_result.get("executed", []) or []

        # Reconcile: any accepted action the engine did not execute is rejected.
        executed_keys = {(e.get("symbol"), e.get("action")) for e in executed}
        for action in accepted_actions:
            key = (action["symbol"], action["action"])
            if key not in executed_keys:
                rejections.append(
                    {"order": action, "reason": _infer_rejection(action, cash_before, prices, positions_before)}
                )

        fills = session.fills_since(trades_before)
        exec_ts = session.executed_step_timestamp()
        portfolio_after = session.protocol_portfolio(exec_ts)
        decision_id = _new_decision_id()
        run_completed = session.status == "completed"

        result = {
            "protocol_version": PROTOCOL_VERSION,
            "run_id": run.run_id,
            "step_id": step_id,
            "decision_id": decision_id,
            "accepted": bool(engine_result.get("accepted")),
            "validation": {
                "passed": len(rejections) == 0,
                "warnings": [],
                "rejections": rejections,
            },
            "fills": fills,
            "portfolio_after": portfolio_after,
            "run_status": "completed" if run_completed else "running",
        }

        # Record finalization + idempotency.
        run.idempotency[decision.idempotency_key] = result
        run.step_results_by_seq[seq] = {
            "idempotency_key": decision.idempotency_key,
            "result": result,
        }
        if step_id in run.step_meta:
            run.step_meta[step_id]["status"] = "completed"

        if run_completed:
            _sync_status(run)

        return result


# ----------------------------------------------------------------------
# Result / log accessors
# ----------------------------------------------------------------------


def list_steps(run_id: str) -> Dict[str, Any]:
    run = _get_run(run_id)
    _sync_status(run)
    decisions = _decisions_raw(run)
    steps = []
    for d in decisions:
        seq = d.get("step_index", 0)
        source = d.get("decision_source")
        status = "timed_out" if source == "timeout_hold" else "completed"
        steps.append({
            "sequence": seq,
            "step_id": run.seq_to_step_id.get(seq),
            "timestamp": d.get("timestamp"),
            "status": status,
            "decision_source": source,
            "actions_executed": d.get("actions_executed", 0),
        })
    return {"protocol_version": PROTOCOL_VERSION, "run_id": run_id, "steps": steps, "count": len(steps)}


def list_decisions(run_id: str) -> Dict[str, Any]:
    run = _get_run(run_id)
    _sync_status(run)
    decisions = _decisions_raw(run)
    return {
        "protocol_version": PROTOCOL_VERSION,
        "run_id": run_id,
        "decisions": decisions,
        "count": len(decisions),
    }


def list_trades(run_id: str) -> Dict[str, Any]:
    run = _get_run(run_id)
    _sync_status(run)
    if run.result_run_id:
        trades = db.get_trades(run.result_run_id)
    else:
        session = run.session()
        trades = _normalize_live_trades(session.manager.trades) if session else []
    return {"protocol_version": PROTOCOL_VERSION, "run_id": run_id, "trades": trades, "count": len(trades)}


def get_metrics(run_id: str) -> Dict[str, Any]:
    run = _get_run(run_id)
    status = _sync_status(run)
    metrics: Dict[str, Any] = {}
    if run.result_run_id:
        dbrun = db.get_run(run.result_run_id)
        if dbrun:
            metrics = {
                "total_return": dbrun.get("total_return"),
                "sharpe_ratio": dbrun.get("sharpe_ratio"),
                "max_drawdown": dbrun.get("max_drawdown"),
                "num_trades": dbrun.get("num_trades"),
                "final_equity": dbrun.get("final_equity"),
                "llm_calls": dbrun.get("llm_calls"),
                "input_tokens": dbrun.get("input_tokens"),
                "output_tokens": dbrun.get("output_tokens"),
                "est_cost_usd": dbrun.get("est_cost_usd"),
            }
    else:
        engine = status["engine_status"] or {}
        metrics = engine.get("metrics") or {}
    return {
        "protocol_version": PROTOCOL_VERSION,
        "run_id": run_id,
        "status": run.status,
        "metrics": metrics,
    }


def get_result(run_id: str) -> Dict[str, Any]:
    run = _get_run(run_id)
    _sync_status(run)
    if not run.result_run_id:
        raise ProtocolError(
            "run_not_completed",
            "Run has not completed; results are not yet available",
            409,
            details={"status": run.status},
        )
    result = ebs.get_run_result(run.result_run_id, run.session_id)
    if result is None:
        raise ProtocolError("result_not_found", "Result not found for this run", 404)
    return {
        "protocol_version": PROTOCOL_VERSION,
        "run_id": run_id,
        "result_run_id": run.result_run_id,
        "status": run.status,
        **result,
    }


# ----------------------------------------------------------------------
# Internal helpers
# ----------------------------------------------------------------------


def _build_step_view(run, session, seq, step_id, step) -> Dict[str, Any]:
    snapshot = step.get("market_snapshot", {})
    portfolio = session.protocol_portfolio(session.timestamps[seq])
    return {
        "protocol_version": PROTOCOL_VERSION,
        "run_id": run.run_id,
        "step_id": step_id,
        "sequence": seq,
        "timestamp": step.get("timestamp"),
        "deadline_at": step.get("decision_deadline_at"),
        "status": "awaiting_decision",
        "observation": {
            "market": {
                "bars": {},
                "features": snapshot.get("top_signals", {}),
                "events": [],
            },
            "portfolio": portfolio,
        },
        "constraints": run.constraints(),
    }


def _historical_step_status(run, seq) -> str:
    prior = run.step_results_by_seq.get(seq)
    if prior:
        return "completed"
    # Fall back to the persisted/engine decision log.
    for d in _decisions_raw(run):
        if d.get("step_index") == seq:
            return "timed_out" if d.get("decision_source") == "timeout_hold" else "completed"
    return "completed"


def _decisions_raw(run) -> List[Dict[str, Any]]:
    if run.result_run_id:
        return db.get_decisions(run.result_run_id)
    session = run.session()
    if session is None:
        return []
    return session.get_decisions()


def _normalize_live_trades(trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for t in trades:
        ts = t.get("timestamp")
        if hasattr(ts, "isoformat"):
            ts = ts.isoformat()
        qty = int(t.get("shares") or 0)
        price = float(t.get("price") or 0)
        out.append({
            "timestamp": ts,
            "symbol": t.get("symbol"),
            "quantity": qty,
            "side": str(t.get("side", "")).upper(),
            "price": price,
            "value": float(t.get("cost") or t.get("proceeds") or qty * price),
            "reason": t.get("reason"),
        })
    return out


def _infer_rejection(action, cash_before, prices, positions_before) -> str:
    side = action["action"]
    symbol = action["symbol"]
    if action.get("confidence", 1.0) < 0.3:
        return "below_min_confidence"
    if side == "sell":
        if positions_before.get(symbol, 0) <= 0:
            return "no_position"
        return "not_executed"
    if side == "buy":
        price = prices.get(symbol, 0)
        if price <= 0:
            return "missing_price"
        if action["position_size"] * price > cash_before:
            return "insufficient_cash"
    return "not_executed"


def _iso(value):
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)
