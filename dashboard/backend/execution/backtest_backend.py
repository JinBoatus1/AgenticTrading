"""BacktestBackend — wraps ExternalBacktestSession behind the ExecutionBackend seam.

Schema parity: build_context/apply_decisions/result emit the typed v2 shapes.
Lifecycle parity: loop == "lockstep" (decision_deadline_at + auto-hold apply).
"""

from __future__ import annotations

import hashlib
import json
import threading
from typing import Any, Dict, List, Optional, Tuple

from dashboard.backend.api.v2.models import SCHEMA_VERSION
from dashboard.backend.database import db
from dashboard.backend.execution.base import ExecutionBackend
from dashboard.backend.infrastructure.llm.validator import DJIA_30
from dashboard.backend.domain.backtesting import external_run_service as ext


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
            except Exception as exc:  # mirror v1 start_backtest behavior
                # Take the session lock: HTTP readers inspect status/error under
                # the same lock (get_current_step/get_status), so the writer must
                # hold it too to avoid a data race on these fields.
                with self.session._step_lock:
                    self.session.status = "failed"
                    self.session.error = str(exc)

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

    def apply_decisions(self, actions: List[Dict[str, Any]]) -> Dict[str, Any]:
        # Actions arrive pre-validated from the v2 boundary (validate_actions);
        # this backend executes them and reports execution results. Schema-level
        # rejections are merged in by the boundary.
        result = self.session.submit_decisions({"actions": actions})

        executed = [
            {"action": e.get("action"), "symbol": e.get("symbol"),
             "shares": e.get("shares"), "price": None}
            for e in (result.get("executed") or [])
        ]

        return {
            "accepted": bool(result.get("accepted", True)),
            "executed": executed,
            "rejected": [],
            "decision_source": result.get("decision_source") or "external_agent",
            "next_step": result.get("next_step", self.session.step_index),
            "status": result.get("status", self.session.status),
            "run_id": self.run_id,
            "metrics": result.get("metrics"),
        }

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

    def result(self) -> Optional[Dict[str, Any]]:
        if not self.session.run_id:
            return None
        base = ext.get_run_result(self.session.run_id, self.session.session_id)
        if base is None:
            return None
        base["manifest"] = db.get_run_manifest(self.run_id)
        return base
