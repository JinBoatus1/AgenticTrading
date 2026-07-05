"""BacktestBackend — wraps ExternalBacktestSession behind the ExecutionBackend seam.

Schema parity: build_context/apply_decisions/result emit the typed v2 shapes.
Lifecycle parity: loop == "lockstep" (decision_deadline_at + auto-hold apply).
"""

from __future__ import annotations

import hashlib
import json
import threading
from typing import Any, Dict, List, Optional, Tuple

from dashboard.backend.api.v2.errors import ApiError
from dashboard.backend.api.v2.models import SCHEMA_VERSION
from dashboard.backend.database import db
from dashboard.backend.execution.base import ExecutionBackend
from dashboard.backend.infrastructure.llm.validator import DJIA_30
from dashboard.backend.domain.backtesting import external_run_service as ext
# Late-bound module reference (run_repo.run_store) so tests that swap the
# run_store singleton cover this module too.
from dashboard.backend.domain.runs import repository as run_repo


def load_news_sentiment(universe: List[str], timestamp: Any) -> Tuple[Dict[str, Any], Optional[str]]:
    """Populate the news_sentiment slot from Plan 1's adapter, fail-closed.

    Plan 1 (dashboard/backend/integrations/news_sentiment.py) is expected to expose
    get_news_sentiment(universe, timestamp) -> {"news_sentiment": {...}, "news_overview": str|None}.
    Until it lands, the slot is guaranteed present and empty.
    """
    try:
        from dashboard.backend.integrations.news_sentiment import get_news_sentiment  # type: ignore
    except Exception:
        return {}, None
    try:
        data = get_news_sentiment(universe, timestamp) or {}
        return data.get("news_sentiment", {}) or {}, data.get("news_overview")
    except Exception:
        return {}, None


def _context_hash(envelope: Dict[str, Any]) -> str:
    payload = json.dumps(envelope, sort_keys=True, default=str)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


class BacktestBackend(ExecutionBackend):
    loop = "lockstep"

    def __init__(self, *, run_id: str, session_id: str, agent_name: str,
                 model_name: str, start_date: str, end_date: str,
                 mode: str = "safe_trading"):
        self.run_id = run_id
        self.session = ext.ExternalBacktestSession(
            backtest_id=run_id, session_id=session_id, agent_name=agent_name,
            model_name=model_name, start_date=start_date, end_date=end_date,
            mode=mode, run_id=run_id,
        )
        self.news_sentiment_source: Optional[str] = None

    # -- lifecycle ---------------------------------------------------------

    def load_blocking(self) -> None:
        self.session.load_market_data()

    def start_background_load(self) -> None:
        def _load() -> None:
            try:
                self.session.load_market_data()
            except (Exception, SystemExit) as exc:  # mirror v1 start_backtest behavior
                # SystemExit too: AlpacaDataLoader sys.exit()s when creds are
                # absent, and a daemon thread swallows an uncaught SystemExit
                # silently — the run would sit in "loading" forever.
                # Take the session lock: HTTP readers inspect status/error under
                # the same lock (get_current_step/get_status), so the writer must
                # hold it too to avoid a data race on these fields.
                with self.session._step_lock:
                    self.session.status = "failed"
                    self.session.error = str(exc)
                # Mirror the failure into the run's protocol_runs row so the
                # unified active-run cap frees this slot without waiting for
                # the reaper's next reconcile pass.
                try:
                    run_repo.run_store.update_run(self.run_id, status="failed")
                except Exception:
                    pass  # row bookkeeping is best-effort; the sweep reconciles

        self.session.status = "loading"
        threading.Thread(target=_load, daemon=True).start()

    def current_step_index(self) -> int:
        return self.session.step_index

    # -- context -----------------------------------------------------------

    def build_context(self) -> Dict[str, Any]:
        step = self.session.get_current_step()
        status = step.get("status")
        base: Dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "mode": "backtest",
            "loop": self.loop,
            "universe": list(DJIA_30),
            "status": status,
            "step_index": self.session.step_index,
            "total_steps": self.session.total_steps,
            "news_sentiment": {},
            "news_overview": None,
        }
        if status != "waiting_decision":
            return base

        snap = step["market_snapshot"]
        sentiment, overview = load_news_sentiment(list(DJIA_30), step.get("timestamp"))
        envelope = {
            **base,
            "step_index": step["step_index"],
            "total_steps": step["total_steps"],
            "timestamp": step["timestamp"],
            "decision_deadline_at": step["decision_deadline_at"],
            "decision_timeout_seconds": step["decision_timeout_seconds"],
            "portfolio": snap["portfolio"],
            "current_holdings": snap["current_holdings"],
            "recent_trades": snap["recent_trades"],
            "top_signals": snap["top_signals"],
            "news_sentiment": sentiment,
            "news_overview": overview,
            "decision_format": step["decision_format"],
        }
        # Record the hash of exactly what we served, keyed by step, for the decision log.
        self.session.context_ref_by_step[step["step_index"]] = _context_hash(envelope)
        return envelope

    # -- decisions ---------------------------------------------------------

    @staticmethod
    def _raise_rejection(result: Dict[str, Any]) -> None:
        """Map the engine's non-accepted submit results to typed v2 errors.

        Flattening them into the ack shape would report a refused submission
        as an accepted-looking decision attributed to "external_agent"."""
        err = str(result.get("error") or "invalid_status")
        if err == "step_already_closed":
            raise ApiError(
                "step_already_closed",
                "The step closed before the decision arrived (step auto-held)",
                status=409, retryable=True,
                details={"outcome": result.get("outcome"),
                         "next_step": result.get("next_step")},
            )
        if err == "backtest_already_completed":
            raise ApiError("invalid_status", "Run already completed", status=409)
        if err.startswith("invalid_status:"):
            state = err.split(":", 1)[1]
            raise ApiError(
                "invalid_status",
                f"Run is not awaiting a decision (status: {state})", status=409,
                retryable=state == "loading",
            )
        # Engine-level payload rejection (parse failure etc.) — the step was
        # auto-held with decision_source="validation_hold" by the engine.
        raise ApiError(
            "validation_failed", err, status=422,
            details={"outcome": result.get("outcome")},
        )

    def apply_decisions(self, actions: List[Dict[str, Any]]) -> Dict[str, Any]:
        # Actions arrive pre-validated from the v2 boundary (validate_actions);
        # this backend executes them and reports execution results. Schema-level
        # rejections are merged in by the boundary.
        result = self.session.submit_decisions({"actions": actions})
        if not result.get("accepted", True):
            self._raise_rejection(result)

        executed = [
            {"action": e.get("action"), "symbol": e.get("symbol"),
             "shares": e.get("shares"), "price": None}
            for e in (result.get("executed") or [])
        ]

        ack = {
            "accepted": bool(result.get("accepted", True)),
            "executed": executed,
            "rejected": [],
            "decision_source": result.get("decision_source") or "external_agent",
            "next_step": result.get("next_step", self.session.step_index),
            "status": result.get("status", self.session.status),
            "run_id": self.run_id,
            "metrics": result.get("metrics"),
        }
        if ack["status"] == "completed":
            # The final submit finalized the run — record the terminal state on
            # its protocol_runs row so cap counting and restart recovery see it.
            try:
                run_repo.run_store.update_run(
                    self.run_id,
                    status="completed",
                    result_run_id=self.session.run_id or self.run_id,
                )
            except Exception:
                pass  # best-effort; the reaper sweep reconciles
        return ack

    def decisions(self) -> List[Dict[str, Any]]:
        return self.session.get_decisions()

    def advance(self) -> None:
        # Lockstep engine advances inside submit; this only applies a pending timeout.
        self.session.get_current_step()

    def cancel(self) -> None:
        self.session.status = "closed"

    # -- status / result ---------------------------------------------------

    def status(self) -> Dict[str, Any]:
        s = self.session.get_status()
        s["mode"] = "backtest"
        s["loop"] = self.loop
        return s

    def is_active(self) -> bool:
        # Deliberately an unlocked attribute read: the cap check runs under the
        # global create lock and must never take _step_lock (get_status can
        # cascade into _maybe_apply_timeout/_finalize). Worst case the cap
        # briefly counts a just-finished run — fine for a resource cap.
        return self.session.status not in ("completed", "failed", "closed")

    def result(self) -> Optional[Dict[str, Any]]:
        if not self.session.run_id:
            return None
        base = ext.get_run_result(self.session.run_id, self.session.session_id)
        if base is None:
            return None
        base["manifest"] = db.get_run_manifest(self.run_id)
        return base


class ArchivedBacktestBackend(ExecutionBackend):
    """DB-backed tombstone for a terminal run whose engine session was freed.

    The reaper swaps this in for a finished BacktestBackend (releasing the
    market-data buffers — ~99% of a session's memory), and the v2 API
    rehydrates one from a terminal protocol_runs row after a restart. Reads
    (status/result/decisions and DB-cached idempotent replays) keep working;
    new decisions get the same invalid_status rejection the live path gives
    for a terminal run.
    """

    loop = "lockstep"

    _TERMINAL = ("completed", "failed", "closed")

    def __init__(self, *, run_id: str, session_id: str, status: str,
                 error: Optional[str] = None, step_index: int = 0,
                 total_steps: int = 0, result_run_id: Optional[str] = None):
        self.run_id = run_id
        self.session_id = session_id
        self.terminal_status = status if status in self._TERMINAL else "failed"
        self.error = error
        self.step_index = int(step_index or 0)
        self.total_steps = int(total_steps or 0)
        self.result_run_id = result_run_id or run_id

    @classmethod
    def from_record(cls, record: Dict[str, Any]) -> "ArchivedBacktestBackend":
        """Rebuild from a terminal protocol_runs row (post-restart reads)."""
        return cls(
            run_id=record["run_id"],
            session_id=record["session_id"],
            status=record.get("status") or "failed",
            result_run_id=record.get("result_run_id"),
        )

    # -- lifecycle: everything is over -------------------------------------

    def is_active(self) -> bool:
        return False

    def current_step_index(self) -> int:
        return self.step_index

    def advance(self) -> None:
        return None

    def cancel(self) -> None:
        return None  # already terminal; do not clobber completed → closed

    # -- reads --------------------------------------------------------------

    def build_context(self) -> Dict[str, Any]:
        # Mirrors the live backend's non-waiting envelope.
        return {
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "mode": "backtest",
            "loop": self.loop,
            "universe": list(DJIA_30),
            "status": self.terminal_status,
            "step_index": self.step_index,
            "total_steps": self.total_steps,
            "news_sentiment": {},
            "news_overview": None,
        }

    def apply_decisions(self, actions: List[Dict[str, Any]]) -> Dict[str, Any]:
        # Same errors the live path raises for a terminal session (via
        # _raise_rejection), so archival is invisible to error handling.
        if self.terminal_status == "completed":
            raise ApiError("invalid_status", "Run already completed", status=409)
        raise ApiError(
            "invalid_status",
            f"Run is not awaiting a decision (status: {self.terminal_status})",
            status=409,
        )

    def status(self) -> Dict[str, Any]:
        base: Dict[str, Any] = {
            "backtest_id": self.run_id,
            "status": self.terminal_status,
            "step_index": self.step_index,
            "total_steps": self.total_steps,
            "run_id": self.result_run_id,
            "mode": "backtest",
            "loop": self.loop,
        }
        manifest = db.get_run_manifest(self.run_id) or {}
        base["agent_name"] = manifest.get("agent_name")
        base["model_name"] = manifest.get("model_name")
        if self.terminal_status == "completed":
            row = db.get_run(self.result_run_id)
            if row:
                base["metrics"] = {
                    "total_return": row.get("total_return"),
                    "sharpe_ratio": row.get("sharpe_ratio"),
                    "max_drawdown": row.get("max_drawdown"),
                    "num_trades": row.get("num_trades"),
                    "final_equity": row.get("final_equity"),
                    "llm_calls": row.get("llm_calls"),
                    "input_tokens": row.get("input_tokens"),
                    "output_tokens": row.get("output_tokens"),
                    "est_cost_usd": row.get("est_cost_usd"),
                }
        if self.error:
            base["error"] = self.error
        return base

    def decisions(self) -> List[Dict[str, Any]]:
        try:
            return db.get_decisions(self.result_run_id)
        except Exception:
            return []

    def result(self) -> Optional[Dict[str, Any]]:
        base = ext.get_run_result(self.result_run_id, self.session_id)
        if base is None:
            return None
        base["manifest"] = db.get_run_manifest(self.run_id)
        return base
