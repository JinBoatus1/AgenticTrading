"""
External agent backtest service — step-by-step hourly loop via HTTP API.

Each trading hour waits up to DECISION_TIMEOUT_SECONDS for POST /decisions;
otherwise the step auto-holds (no trades).

Canonical location (Phase 3C1). Moved verbatim from
``dashboard/backend/external_backtest_service.py``; the original module was
removed in Phase 4A. Public classes, functions, constants, singletons,
signatures, return schemas, exceptions, logging, persistence, result
serialization, and backtest orchestration are unchanged; only the module
location moved.
"""

from __future__ import annotations

import os
import uuid
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import pandas as pd
import pytz

import dashboard.backend.infrastructure.llm.token_cost as token_cost
from dashboard.backend.domain.agents.repository import agent_store
from dashboard.backend.database import db
from dashboard.backend.infrastructure.llm.validator import (
    DJIA_30,
    actions_to_executable,
    parse_actions_payload,
)
from dashboard.backend.domain.backtesting.constants import INITIAL_CAPITAL
from dashboard.backend.domain.backtesting.features import TechnicalIndicators
from dashboard.backend.domain.backtesting.metrics import (
    calculate_max_drawdown,
    calculate_sharpe,
)
from dashboard.backend.domain.backtesting.portfolio_manager import PortfolioManager
from dashboard.backend.infrastructure.market_data.alpaca_bars import AlpacaDataLoader

from dashboard.backend.domain.backtesting.engine import HourlyBacktester

DECISION_TIMEOUT_SECONDS = int(os.getenv("EXTERNAL_AGENT_DECISION_TIMEOUT_SECONDS", "30"))
ET_TZ = pytz.timezone("US/Eastern")

_sessions: Dict[str, "ExternalBacktestSession"] = {}
_lock = threading.Lock()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _new_ext_run_id() -> str:
    """Unique id for a finalized external run.

    Second-resolution timestamp for human-readable ordering PLUS a uuid suffix.
    The bare ``ext_<YYYYMMDD_HHMMSS>`` scheme used before collided when two runs
    finalized in the same second: the id is a PRIMARY KEY written with
    ``INSERT OR REPLACE``, so a collision silently overwrote the earlier run's
    rows — and a cached ``/runs/{id}/plot.png`` would then serve the wrong run's
    chart forever. Only ``str.startswith("ext_")`` and a ``created_at`` sort ever
    depend on this value, so the suffix is safe.
    """
    return f"ext_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"


class ExternalBacktestSession:
    """One external-agent backtest driven hour-by-hour through the API."""

    def __init__(
        self,
        *,
        backtest_id: str,
        session_id: str,
        agent_name: str,
        model_name: str,
        start_date: str,
        end_date: str,
        mode: str = "safe_trading",
        symbols: Optional[List[str]] = None,
        run_id: Optional[str] = None,
    ):
        self.backtest_id = backtest_id
        self.session_id = session_id
        self.agent_name = agent_name
        self.model_name = model_name
        self.start_date = start_date
        self.end_date = end_date
        self.mode = mode
        # Declared tradeable allow-list (protocol runs' config.symbols).
        # When set, market snapshots carry features for every one of these
        # symbols; when None (legacy external flow), the historical top-10
        # RSI sampling is preserved.
        self.symbols = list(symbols) if symbols else None

        self.status = "loading"
        self.error: Optional[str] = None
        self.step_index = 0
        self.total_steps = 0
        self.run_id: Optional[str] = run_id
        self.baseline_run_ids: Dict[str, str] = {}
        # v2 backends record the hash of the exact context served per step here;
        # threaded into the decision log so each decision traces to its context.
        self.context_ref_by_step: Dict[int, str] = {}

        self.manager = PortfolioManager(initial_capital=INITIAL_CAPITAL)
        self.all_data: Dict[str, pd.DataFrame] = {}
        self.timestamps: List[Any] = []
        self.price_cache: Dict[str, Dict[Any, float]] = {}

        self.step_opened_at: Optional[datetime] = None
        self.last_decision_source: Optional[str] = None
        self.decision_log: List[Dict[str, Any]] = []
        self.last_executed: List[Dict[str, Any]] = []

        # Estimated token usage. The agent's LLM runs client-side, so we
        # approximate input tokens from the context we serve each hour and
        # output tokens from the decisions the agent submits.
        self.llm_calls = 0
        self.est_input_tokens = 0
        self.est_output_tokens = 0

        self._step_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def load_market_data(self) -> None:
        loader = AlpacaDataLoader()
        self.all_data = loader.fetch_bars(DJIA_30, self.start_date, self.end_date)
        if not self.all_data:
            raise RuntimeError("No market data returned from Alpaca")

        for symbol, df in self.all_data.items():
            self.all_data[symbol] = TechnicalIndicators.calculate_indicators(df)

        self.timestamps = self._build_trading_timestamps()
        self.total_steps = len(self.timestamps)
        self.price_cache = self._build_price_cache()

        if self.total_steps == 0:
            raise RuntimeError("No trading hours in the selected date range")

        self.status = "waiting_decision"
        self._open_current_step()

    def _build_trading_timestamps(self) -> List[Any]:
        all_timestamps: set = set()
        for df in self.all_data.values():
            all_timestamps.update(df.index)
        ordered = sorted(all_timestamps)

        min_required = int(len(self.all_data) * 0.8)
        filtered = []
        for ts in ordered:
            real_count = sum(1 for df in self.all_data.values() if ts in df.index)
            if real_count >= min_required:
                filtered.append(ts)
        ordered = filtered if filtered else ordered

        market_hours = []
        for ts in ordered:
            ts_et = ts.astimezone(ET_TZ)
            hour, minute = ts_et.hour, ts_et.minute
            is_market = (
                (hour > 9 and hour < 16)
                or (hour == 9 and minute >= 30)
                or (hour == 16 and minute == 0)
            )
            if is_market:
                market_hours.append(ts)
        return market_hours

    def _build_price_cache(self) -> Dict[str, Dict[Any, float]]:
        cache: Dict[str, Dict[Any, float]] = {}
        for symbol, df in self.all_data.items():
            cache[symbol] = {}
            last_price = None
            for timestamp in self.timestamps:
                if timestamp in df.index:
                    last_price = df.loc[timestamp, "close"]
                    cache[symbol][timestamp] = float(last_price)
                elif last_price is not None:
                    cache[symbol][timestamp] = float(last_price)
        return cache

    def _market_data_at(self, timestamp) -> Dict[str, pd.Series]:
        market_data = {}
        for symbol in DJIA_30:
            if symbol not in self.all_data:
                continue
            df = self.all_data[symbol]
            if timestamp in df.index:
                market_data[symbol] = df.loc[timestamp]
        return market_data

    def _open_current_step(self) -> None:
        self.step_opened_at = _utcnow()
        self.last_decision_source = None

    def _deadline_at(self) -> datetime:
        opened = self.step_opened_at or _utcnow()
        return opened + timedelta(seconds=DECISION_TIMEOUT_SECONDS)

    # ------------------------------------------------------------------
    # Snapshot for external agents
    # ------------------------------------------------------------------

    def build_market_snapshot(self, portfolio_state: Dict[str, Any]) -> Dict[str, Any]:
        timestamp = portfolio_state.get("timestamp", datetime.now())
        if hasattr(timestamp, "isoformat"):
            timestamp_str = timestamp.isoformat()
        else:
            timestamp_str = str(timestamp)

        holdings = {}
        for position in portfolio_state["positions"]:
            holdings[position["symbol"]] = {
                "shares": position["shares"],
                "entry_price": round(position["entry_price"], 2),
                "current_price": round(position["current_price"], 2),
                "position_value": round(position["position_value"], 2),
                "pnl_pct": round(position["pnl_pct"], 2),
            }

        recent_trades = []
        cutoff = timestamp - timedelta(hours=24)
        for trade in self.manager.trades:
            if trade["timestamp"] > cutoff:
                recent_trades.append({
                    "symbol": trade["symbol"],
                    "side": trade["side"],
                    "shares": trade["shares"],
                    "price": round(float(trade["price"]), 2),
                    "timestamp": trade["timestamp"].isoformat()
                    if hasattr(trade["timestamp"], "isoformat")
                    else str(trade["timestamp"]),
                })

        snapshot: Dict[str, Any] = {
            "timestamp": timestamp_str,
            "portfolio": {
                "cash": round(portfolio_state["cash"], 2),
                "positions_value": round(portfolio_state["positions_value"], 2),
                "total_equity": round(portfolio_state["total_equity"], 2),
                "num_positions": len(portfolio_state["positions"]),
            },
            "current_holdings": holdings,
            "recent_trades": recent_trades,
            "top_signals": {},
        }

        signals = portfolio_state["market_signals"]
        if self.symbols:
            # Protocol runs declare a tradeable allow-list: the agent must see
            # features for every symbol it may trade (it can't trade what it
            # can't see). No LLM prompt is built from this snapshot on the
            # external path, so there is no prompt-size reason to sample.
            symbols = [s for s in self.symbols if s in signals]
        elif self.mode == "buy_and_hold":
            symbols = [s for s in DJIA_30 if s in signals]
        else:
            rsi_sorted = sorted(
                [(sym, sig.get("rsi", 50)) for sym, sig in signals.items()],
                key=lambda x: abs(x[1] - 50),
                reverse=True,
            )
            symbols = [sym for sym, _ in rsi_sorted[:10]]

        for symbol in symbols:
            signal = signals[symbol]
            snapshot["top_signals"][symbol] = {
                "price": float(signal.get("price") or 0),
                "rsi": float(signal.get("rsi") if pd.notna(signal.get("rsi")) else 50),
                "macd": float(signal.get("macd") if pd.notna(signal.get("macd")) else 0),
                "macd_signal": float(
                    signal.get("macd_signal") if pd.notna(signal.get("macd_signal")) else 0
                ),
                "sma20": float(signal.get("sma20") if pd.notna(signal.get("sma20")) else 0),
                "sma50": float(signal.get("sma50") if pd.notna(signal.get("sma50")) else 0),
                "bb_upper": float(
                    signal.get("bb_upper") if pd.notna(signal.get("bb_upper")) else 0
                ),
                "bb_lower": float(
                    signal.get("bb_lower") if pd.notna(signal.get("bb_lower")) else 0
                ),
            }

        return snapshot

    # ------------------------------------------------------------------
    # Step API
    # ------------------------------------------------------------------

    def _build_step_context(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """The payload an agent consumes to decide — used as the input estimate."""
        return {
            "market_snapshot": self.build_market_snapshot(state),
            "valid_symbols": DJIA_30,
            "decision_format": get_decision_format(),
        }

    def _account_step_tokens(
        self,
        state: Dict[str, Any],
        decision_payload: Dict[str, Any],
    ) -> None:
        """Accumulate estimated input/output tokens for one agent decision."""
        try:
            self.est_input_tokens += token_cost.estimate_tokens(
                self._build_step_context(state)
            )
            self.est_output_tokens += token_cost.estimate_tokens(decision_payload)
            self.llm_calls += 1
        except Exception as exc:  # never let estimation break a backtest
            print(f"⚠️ Token estimate skipped for step {self.step_index}: {exc}")

    def _maybe_apply_timeout(self) -> bool:
        """Auto-hold if the decision window expired. Returns True if advanced."""
        if self.status != "waiting_decision":
            return False
        if _utcnow() <= self._deadline_at():
            return False
        self._advance_step(executable=[], decision_source="timeout_hold")
        return True

    def get_current_step(self) -> Dict[str, Any]:
        with self._step_lock:
            while self._maybe_apply_timeout():
                if self.status == "completed":
                    break

            if self.status == "loading":
                return {"status": "loading", "message": "Loading market data..."}

            if self.status == "failed":
                return {"status": "failed", "error": self.error}

            if self.status == "completed":
                return {
                    "status": "completed",
                    "backtest_id": self.backtest_id,
                    "run_id": self.run_id,
                    "baseline_run_ids": self.baseline_run_ids,
                    "total_steps": self.total_steps,
                    "metrics": self._final_metrics(),
                    "compare_url": self._compare_url(),
                    "session_id": self.session_id,
                }

            if self.status == "closed":
                return {
                    "status": "closed",
                    "backtest_id": self.backtest_id,
                    "run_id": self.run_id,
                    "step_index": self.step_index,
                    "total_steps": self.total_steps,
                    "session_id": self.session_id,
                }

            timestamp = self.timestamps[self.step_index]
            market_data = self._market_data_at(timestamp)
            state = self.manager.get_portfolio_state(
                market_data, self.price_cache, timestamp
            )
            state["timestamp"] = timestamp

            return {
                "status": "waiting_decision",
                "backtest_id": self.backtest_id,
                "step_index": self.step_index,
                "total_steps": self.total_steps,
                "timestamp": timestamp.isoformat()
                if hasattr(timestamp, "isoformat")
                else str(timestamp),
                "decision_timeout_seconds": DECISION_TIMEOUT_SECONDS,
                "decision_deadline_at": _iso(self._deadline_at()),
                "market_snapshot": self.build_market_snapshot(state),
                "valid_symbols": DJIA_30,
                "decision_format": get_decision_format(),
            }

    def submit_decisions(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self._step_lock:
            if self.status == "completed":
                return {
                    "accepted": False,
                    "error": "backtest_already_completed",
                    "run_id": self.run_id,
                }

            if self.status != "waiting_decision":
                return {
                    "accepted": False,
                    "error": f"invalid_status:{self.status}",
                }

            if _utcnow() > self._deadline_at():
                self._advance_step(executable=[], decision_source="timeout_hold")
                return {
                    "accepted": False,
                    "error": "step_already_closed",
                    "outcome": "timeout_hold",
                    "next_step": self.step_index,
                    "status": self.status,
                }

            decisions, err = parse_actions_payload(payload)
            if err:
                self._advance_step(executable=[], decision_source="validation_hold")
                return {
                    "accepted": False,
                    "error": err,
                    "outcome": "validation_hold",
                    "next_step": self.step_index,
                    "status": self.status,
                }

            timestamp = self.timestamps[self.step_index]
            market_data = self._market_data_at(timestamp)
            state = self.manager.get_portfolio_state(
                market_data, self.price_cache, timestamp
            )
            state["timestamp"] = timestamp
            self._account_step_tokens(state, payload)
            current_prices = {
                sym: float(row.get("price", 0))
                for sym, row in state["market_signals"].items()
            }

            executable = actions_to_executable(
                decisions,
                cash=self.manager.cash,
                positions=self.manager.positions,
                current_prices=current_prices,
            )

            self._advance_step(
                executable=executable,
                decision_source="external_agent",
                raw_actions=[d.model_dump() for d in decisions],
            )

            return {
                "accepted": True,
                "executed_count": len(self.last_executed),
                "executed": self.last_executed,
                "decision_source": self.last_decision_source,
                "next_step": self.step_index,
                "status": self.status,
                "run_id": self.run_id if self.status == "completed" else None,
                "compare_url": self._compare_url() if self.status == "completed" else None,
                "metrics": self._final_metrics() if self.status == "completed" else None,
            }

    def _advance_step(
        self,
        *,
        executable: List[Dict[str, Any]],
        decision_source: str,
        raw_actions: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        timestamp = self.timestamps[self.step_index]
        market_data = self._market_data_at(timestamp)

        self.last_executed = []
        for action in executable:
            self.last_executed.append({
                "symbol": action.get("symbol"),
                "action": action.get("action"),
                "shares": action.get("shares"),
                "reason": action.get("reason"),
            })

        self.manager.execute_actions(executable, market_data, timestamp)
        self.manager.update_equity(market_data, self.price_cache, timestamp)

        self.decision_log.append({
            "step_index": self.step_index,
            "timestamp": timestamp.isoformat()
            if hasattr(timestamp, "isoformat")
            else str(timestamp),
            "decision_source": decision_source,
            "actions_submitted": raw_actions or [],
            "actions_executed": len(executable),
            "context_ref": self.context_ref_by_step.get(self.step_index),
        })
        self.last_decision_source = decision_source

        self.step_index += 1
        if self.step_index >= self.total_steps:
            self._finalize()
        else:
            self.status = "waiting_decision"
            self._open_current_step()

    def _finalize(self) -> None:
        equity_curve = self.manager.get_equity_curve()
        for entry in equity_curve:
            if hasattr(entry["timestamp"], "isoformat"):
                entry["timestamp"] = entry["timestamp"].isoformat()

        # v2 backends pre-assign a canonical run_id at creation; only the
        # legacy flow (no pre-set id) mints the collision-safe ext_ id here.
        if not self.run_id:
            self.run_id = _new_ext_run_id()
        initial_eq = equity_curve[0]["equity"] if equity_curve else INITIAL_CAPITAL
        final_eq = equity_curve[-1]["equity"] if equity_curve else INITIAL_CAPITAL
        total_return = (final_eq - INITIAL_CAPITAL) / INITIAL_CAPITAL

        est_cost = token_cost.estimate_cost_usd(
            self.model_name, self.est_input_tokens, self.est_output_tokens
        )

        db.insert_run(
            run_id=self.run_id,
            session_id=self.session_id,
            agent_name=self.agent_name,
            mode="backtest",
            start_date=self.start_date,
            end_date=self.end_date,
            initial_equity=initial_eq,
            final_equity=final_eq,
            total_return=total_return,
            sharpe_ratio=calculate_sharpe(equity_curve),
            max_drawdown=calculate_max_drawdown(equity_curve),
            num_trades=len(self.manager.trades),
            llm_model=self.model_name,
            llm_calls=self.llm_calls,
            input_tokens=self.est_input_tokens,
            output_tokens=self.est_output_tokens,
            est_cost_usd=est_cost,
        )
        db.insert_equity_points(self.run_id, equity_curve)
        db.insert_trades(self.run_id, self.manager.trades)
        db.insert_decisions(self.run_id, self.decision_log)

        try:
            backtester = HourlyBacktester(
                self.start_date,
                self.end_date,
                self.session_id,
                use_llm=False,
                mode=self.mode,
            )
            backtester.all_data = self.all_data
            buyhold_id, _ = backtester.run_buyhold_baseline()
            djia_id, _ = backtester.run_djia_baseline()
            if buyhold_id:
                self.baseline_run_ids["buy_and_hold"] = buyhold_id
            if djia_id:
                self.baseline_run_ids["djia"] = djia_id
            db.update_run_baselines(
                self.run_id,
                djia_run_id=djia_id,
                buyhold_run_id=buyhold_id,
            )
        # Baseline generation is strictly best-effort and must never break — or
        # hang — run finalization. AlpacaDataLoader raises SystemExit (a
        # BaseException, not Exception) when credentials are absent; if that
        # escaped here it would propagate into the ASGI worker and wedge the
        # request future forever. Catch SystemExit alongside Exception so a
        # credential-less environment degrades to "run saved, no baselines".
        except (Exception, SystemExit) as exc:
            print(f"⚠️ Baseline generation failed (run saved): {exc}")

        try:
            agent_store.register_or_get_agent(
                session_id=self.session_id,
                name=self.agent_name,
                model_name=self.model_name,
            )
        except Exception as exc:
            print(f"⚠️ Agent auto-register failed (run saved): {exc}")

        self.status = "completed"

    def _compare_url(self) -> Optional[str]:
        if not self.run_id:
            return None
        ids = [self.run_id]
        if self.baseline_run_ids.get("djia"):
            ids.append(self.baseline_run_ids["djia"])
        if self.baseline_run_ids.get("buy_and_hold"):
            ids.append(self.baseline_run_ids["buy_and_hold"])
        return f"/compare?run_ids={','.join(ids)}"

    def _final_metrics(self) -> Dict[str, Any]:
        if not self.run_id:
            return {}
        run = db.get_run(self.run_id)
        if not run:
            return {}
        return {
            "total_return": run.get("total_return"),
            "sharpe_ratio": run.get("sharpe_ratio"),
            "max_drawdown": run.get("max_drawdown"),
            "num_trades": run.get("num_trades"),
            "final_equity": run.get("final_equity"),
            "llm_calls": run.get("llm_calls"),
            "input_tokens": run.get("input_tokens"),
            "output_tokens": run.get("output_tokens"),
            "est_cost_usd": run.get("est_cost_usd"),
        }

    def get_status(self) -> Dict[str, Any]:
        with self._step_lock:
            self._maybe_apply_timeout()
            base = {
                "backtest_id": self.backtest_id,
                "status": self.status,
                "step_index": self.step_index,
                "total_steps": self.total_steps,
                "agent_name": self.agent_name,
                "model_name": self.model_name,
                "run_id": self.run_id,
            }
            if self.status == "waiting_decision":
                base["decision_deadline_at"] = _iso(self._deadline_at())
            if self.status == "completed":
                base["metrics"] = self._final_metrics()
                base["baseline_run_ids"] = self.baseline_run_ids
                base["compare_url"] = self._compare_url()
            if self.error:
                base["error"] = self.error
            return base

    def drain_expired(self) -> str:
        """Apply any elapsed decision deadlines (auto-hold) without an agent,
        driving an abandoned run forward. No-op unless the current step is past
        its deadline. Returns the resulting status."""
        with self._step_lock:
            while self._maybe_apply_timeout():
                if self.status == "completed":
                    break
            return self.status

    def get_decisions(self) -> List[Dict[str, Any]]:
        with self._step_lock:
            return list(self.decision_log)

    # ------------------------------------------------------------------
    # Protocol adapters (read-only; used by the Agent-Environment Protocol)
    # ------------------------------------------------------------------

    def _portfolio_state_at(self, timestamp) -> Dict[str, Any]:
        market_data = self._market_data_at(timestamp)
        state = self.manager.get_portfolio_state(market_data, self.price_cache, timestamp)
        state["timestamp"] = timestamp
        return state

    def protocol_portfolio(self, timestamp=None) -> Dict[str, Any]:
        """Normalized {cash, equity, positions[]} snapshot for the protocol."""
        if timestamp is None and self.timestamps:
            idx = self.step_index if self.step_index < self.total_steps else self.total_steps - 1
            idx = max(0, idx)
            timestamp = self.timestamps[idx]
        if timestamp is None:
            return {
                "cash": round(self.manager.cash, 2),
                "equity": round(self.manager.cash, 2),
                "positions": [],
            }
        state = self._portfolio_state_at(timestamp)
        positions = [
            {
                "symbol": p["symbol"],
                "quantity": p["shares"],
                "entry_price": round(p["entry_price"], 4),
                "current_price": round(p["current_price"], 4),
                "market_value": round(p["position_value"], 2),
                "unrealized_pnl_pct": round(p["pnl_pct"], 4),
            }
            for p in state["positions"]
        ]
        return {
            "cash": round(state["cash"], 2),
            "equity": round(state["total_equity"], 2),
            "positions": positions,
        }

    def protocol_current_prices(self, timestamp=None) -> Dict[str, float]:
        if timestamp is None and self.timestamps:
            idx = max(0, min(self.step_index, self.total_steps - 1))
            timestamp = self.timestamps[idx]
        if timestamp is None:
            return {}
        state = self._portfolio_state_at(timestamp)
        return {
            sym: float(sig.get("price") or 0)
            for sym, sig in state["market_signals"].items()
        }

    def executed_step_timestamp(self):
        """Timestamp of the most recently advanced step (post-submit)."""
        if self.step_index > 0 and self.timestamps:
            return self.timestamps[self.step_index - 1]
        return None

    def trade_count(self) -> int:
        return len(self.manager.trades)

    def fills_since(self, baseline_count: int) -> List[Dict[str, Any]]:
        new_trades = self.manager.trades[baseline_count:]
        fills: List[Dict[str, Any]] = []
        for trade in new_trades:
            qty = int(trade.get("shares") or 0)
            fills.append({
                "symbol": trade.get("symbol"),
                "side": str(trade.get("side", "")).lower(),
                "requested_quantity": qty,
                "filled_quantity": qty,
                "fill_price": round(float(trade.get("price") or 0), 4),
            })
        return fills


def get_decision_format() -> Dict[str, Any]:
    """Document the expected external agent decision payload."""
    return {
        "actions": [
            {
                "action": "buy|sell|hold",
                "symbol": "<DJIA symbol>",
                "confidence": 0.0,
                "reasoning": "<short reason>",
                "position_size": 0,
                "stop_loss_price": None,
                "take_profit_price": None,
            }
        ]
    }


def verify_session(session: ExternalBacktestSession, session_id: str) -> bool:
    return session.session_id == session_id


# ------------------------------------------------------------------
# Public registry
# ------------------------------------------------------------------


def start_backtest(
    *,
    session_id: str,
    agent_name: str,
    model_name: str,
    start_date: str,
    end_date: str,
    mode: str = "safe_trading",
    symbols: Optional[List[str]] = None,
) -> Dict[str, Any]:
    backtest_id = f"bt_{uuid.uuid4().hex[:12]}"
    session = ExternalBacktestSession(
        backtest_id=backtest_id,
        session_id=session_id,
        agent_name=agent_name,
        model_name=model_name,
        start_date=start_date,
        end_date=end_date,
        mode=mode,
        symbols=symbols,
    )
    session.status = "loading"

    with _lock:
        _sessions[backtest_id] = session

    def _load_in_background() -> None:
        # load_market_data() constructs AlpacaDataLoader, which raises SystemExit
        # (a BaseException, not Exception) when credentials are absent. On this
        # daemon thread the default threading.excepthook silently swallows
        # SystemExit, so the thread would die without ever marking the session
        # failed — leaving the run stuck in "loading" forever. Catch SystemExit
        # alongside Exception so a credential-less environment fails the run
        # cleanly instead of stranding it. (Mirrors the _finalize() catch above.)
        try:
            session.load_market_data()
        except (Exception, SystemExit) as exc:
            session.status = "failed"
            session.error = str(exc)

    threading.Thread(target=_load_in_background, daemon=True).start()

    return {
        "backtest_id": backtest_id,
        "status": "loading",
        "total_steps": 0,
        "current_step": 0,
        "agent_name": agent_name,
        "model_name": model_name,
        "session_id": session_id,
        "decision_timeout_seconds": DECISION_TIMEOUT_SECONDS,
        "decision_format": get_decision_format(),
        "message": "Loading market data from Alpaca (poll /steps/current)",
        "next": {
            "get_context": f"/api/v1/backtest/{backtest_id}/steps/current",
            "submit_decisions": f"/api/v1/backtest/{backtest_id}/steps/current/decisions",
            "status": f"/api/v1/backtest/{backtest_id}/status",
        },
    }


def get_session(backtest_id: str) -> Optional[ExternalBacktestSession]:
    with _lock:
        return _sessions.get(backtest_id)


def evict_session(backtest_id: str) -> bool:
    """Drop a finished session from memory (frees its market-data buffers).
    Read paths for a completed run fall back to the persisted result run, so
    evicting a terminal session is safe. Returns True if one was removed."""
    with _lock:
        return _sessions.pop(backtest_id, None) is not None


def get_current_step(backtest_id: str) -> Optional[Dict[str, Any]]:
    session = get_session(backtest_id)
    if not session:
        return None
    return session.get_current_step()


def submit_decisions(backtest_id: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    session = get_session(backtest_id)
    if not session:
        return None
    return session.submit_decisions(payload)


def get_status(backtest_id: str) -> Optional[Dict[str, Any]]:
    session = get_session(backtest_id)
    if not session:
        return None
    return session.get_status()


def get_backtest_decisions(backtest_id: str) -> Optional[List[Dict[str, Any]]]:
    session = get_session(backtest_id)
    if not session:
        return None
    return session.get_decisions()


def get_run_trades(run_id: str, session_id: str) -> Optional[List[Dict]]:
    run = db.get_run_with_session(run_id, session_id)
    if not run:
        return None
    return db.get_trades(run_id)


def get_run_decisions(run_id: str, session_id: str) -> Optional[List[Dict]]:
    run = db.get_run_with_session(run_id, session_id)
    if not run:
        return None
    return db.get_decisions(run_id)


def get_run_result(run_id: str, session_id: str) -> Optional[Dict[str, Any]]:
    run = db.get_run_with_session(run_id, session_id)
    if not run:
        return None
    equity = db.get_equity_curve(run_id)
    trades = db.get_trades(run_id)
    decisions = db.get_decisions(run_id)
    return {
        "run": run,
        "equity_curve": equity,
        "trades": trades,
        "decisions": decisions,
        "metrics": {
            "total_return": run.get("total_return"),
            "sharpe_ratio": run.get("sharpe_ratio"),
            "max_drawdown": run.get("max_drawdown"),
            "num_trades": run.get("num_trades"),
            "final_equity": run.get("final_equity"),
            "llm_calls": run.get("llm_calls"),
            "input_tokens": run.get("input_tokens"),
            "output_tokens": run.get("output_tokens"),
            "est_cost_usd": run.get("est_cost_usd"),
        },
    }
