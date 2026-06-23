"""Leaderboard contest: baseline strategies on a fixed backtest window.

Canonical location (Phase 3C3). Moved from
``dashboard/backend/services/leaderboard_service.py``, which is now a thin
compatibility re-export shim. Public functions, ranking behavior, filtering,
ordering, metrics, result schemas, constants, and database behavior are
unchanged; only the module location and the leaderboard-domain import paths
moved.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import dashboard.backend.infrastructure.llm.token_cost as token_cost
from dashboard.backend.database import db
from dashboard.backend.domain.leaderboard.baselines import (
    INITIAL_CAPITAL,
    calc_metrics,
    downsample_daily,
    fetch_hourly_bars,
)
from dashboard.backend.domain.leaderboard.strategies import get_strategy
from dashboard.backend.paths import CONFIG_DIR

LEADERBOARD_MODE = "leaderboard"


def _auto_compute(strategy: Dict[str, Any]) -> bool:
    """Whether a strategy is cheap enough to compute on-demand during a web request.

    LLM-backed entries make real API calls, so they default to manual deploy
    (precomputed by scripts/deploy_leaderboard_model.py) and are flagged with
    ``"auto_compute": false`` in the config.
    """
    return bool(strategy.get("auto_compute", True))


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_leaderboard_config() -> Dict[str, Any]:
    path = CONFIG_DIR / "leaderboard.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _run_id(strategy_id: str, start_date: str, end_date: str) -> str:
    return f"lb_{strategy_id}_{start_date.replace('-', '')}_{end_date.replace('-', '')}"


def _find_cached_run(strategy_id: str, start_date: str, end_date: str, session_id: str) -> Optional[Dict[str, Any]]:
    for run in db.get_runs_by_session(session_id) or []:
        if (
            run.get("mode") == LEADERBOARD_MODE
            and run.get("start_date") == start_date
            and run.get("end_date") == end_date
            and run.get("llm_model") == strategy_id
        ):
            return run
    return None


def _symbols_for_config(config: Dict[str, Any]) -> List[str]:
    symbols: set[str] = set()
    for strategy in config.get("strategies", []):
        symbols.update(get_strategy(strategy).required_symbols())
    return sorted(symbols)


def ensure_leaderboard_runs(force_refresh: bool = False) -> Dict[str, Any]:
    """Compute and persist leaderboard baselines if missing."""
    config = load_leaderboard_config()
    session_id = config["session_id"]
    start_date = config["start_date"]
    end_date = config["end_date"]
    initial_capital = float(config.get("initial_capital", INITIAL_CAPITAL))

    needs_fetch = force_refresh
    for strategy in config.get("strategies", []):
        if not _auto_compute(strategy):
            continue  # LLM models are deployed manually, never block a request
        if force_refresh:
            continue
        if not _find_cached_run(strategy["id"], start_date, end_date, session_id):
            needs_fetch = True
            break

    bars_by_symbol = None
    if needs_fetch:
        bars_by_symbol = fetch_hourly_bars(_symbols_for_config(config), start_date, end_date)
        if not bars_by_symbol:
            raise RuntimeError("No market data returned for leaderboard window")

    created = 0
    for strategy in config.get("strategies", []):
        strategy_id = strategy["id"]
        if not _auto_compute(strategy):
            continue  # deployed via deploy_model_run(), not on-demand
        existing = None if force_refresh else _find_cached_run(
            strategy_id, start_date, end_date, session_id
        )
        if existing and not force_refresh:
            continue

        strategy_impl = get_strategy(strategy)
        bars = bars_by_symbol or fetch_hourly_bars(
            _symbols_for_config(config), start_date, end_date
        )
        curve = strategy_impl.run(bars, start_date, end_date, initial_capital)
        if not curve:
            raise RuntimeError(f"No equity curve for strategy {strategy_id}")

        metrics = calc_metrics(curve, initial_capital)
        run_id = _run_id(strategy_id, start_date, end_date)

        db.insert_run(
            run_id=run_id,
            session_id=session_id,
            agent_name=strategy["name"],
            mode=LEADERBOARD_MODE,
            start_date=start_date,
            end_date=end_date,
            initial_equity=metrics["initial_equity"],
            final_equity=metrics["final_equity"],
            total_return=metrics["total_return"],
            sharpe_ratio=metrics["sharpe_ratio"],
            max_drawdown=metrics["max_drawdown"],
            num_trades=strategy_impl.num_trades(),
            llm_model=strategy_id,
        )
        db.insert_equity_points(run_id, curve)
        created += 1

    return {
        "session_id": session_id,
        "start_date": start_date,
        "end_date": end_date,
        "created": created,
        "refreshed_at": _utcnow_iso(),
    }


def deploy_model_run(
    entry_id: str,
    *,
    force_refresh: bool = False,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Compute and persist one (expensive) leaderboard model entry.

    Used by scripts/deploy_leaderboard_model.py to "deploy" an LLM model onto the
    leaderboard: it runs the model's hourly backtest over the contest window,
    stores the equity curve + metrics + token cost, and caches it so the web
    leaderboard can display it without recomputing. Pass start/end to test on a
    shorter window (writes a separate cached run for that window).
    """
    config = load_leaderboard_config()
    session_id = config["session_id"]
    start_date = start_date or config["start_date"]
    end_date = end_date or config["end_date"]
    initial_capital = float(config.get("initial_capital", INITIAL_CAPITAL))

    entry = next(
        (s for s in config.get("strategies", []) if s.get("id") == entry_id),
        None,
    )
    if entry is None:
        available = [s.get("id") for s in config.get("strategies", [])]
        raise ValueError(f"Unknown leaderboard entry '{entry_id}'. Available: {available}")

    existing = _find_cached_run(entry_id, start_date, end_date, session_id)
    if existing and not force_refresh:
        return {
            "entry_id": entry_id,
            "run_id": existing["run_id"],
            "cached": True,
            "model": entry.get("model"),
            "total_return": existing.get("total_return"),
            "sharpe_ratio": existing.get("sharpe_ratio"),
            "max_drawdown": existing.get("max_drawdown"),
            "final_equity": existing.get("final_equity"),
            "num_trades": existing.get("num_trades"),
            "llm_calls": existing.get("llm_calls"),
            "input_tokens": existing.get("input_tokens"),
            "output_tokens": existing.get("output_tokens"),
            "est_cost_usd": existing.get("est_cost_usd"),
        }

    strategy_impl = get_strategy(entry)
    bars = fetch_hourly_bars(strategy_impl.required_symbols(), start_date, end_date)
    if not bars:
        raise RuntimeError("No market data returned for the contest window")

    curve = strategy_impl.run(bars, start_date, end_date, initial_capital)
    if not curve:
        raise RuntimeError(f"No equity curve produced for entry '{entry_id}'")

    metrics = calc_metrics(curve, initial_capital)
    run_id = _run_id(entry_id, start_date, end_date)

    input_tokens = int(getattr(strategy_impl, "input_tokens", 0) or 0)
    output_tokens = int(getattr(strategy_impl, "output_tokens", 0) or 0)
    llm_calls = int(getattr(strategy_impl, "llm_calls", 0) or 0)
    model_id = getattr(strategy_impl, "model_id", None) or entry.get("model_id")
    est_cost = token_cost.estimate_cost_usd(model_id, input_tokens, output_tokens)

    db.insert_run(
        run_id=run_id,
        session_id=session_id,
        agent_name=entry["name"],
        mode=LEADERBOARD_MODE,
        start_date=start_date,
        end_date=end_date,
        initial_equity=metrics["initial_equity"],
        final_equity=metrics["final_equity"],
        total_return=metrics["total_return"],
        sharpe_ratio=metrics["sharpe_ratio"],
        max_drawdown=metrics["max_drawdown"],
        num_trades=strategy_impl.num_trades(),
        llm_model=entry_id,
        llm_calls=llm_calls,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        est_cost_usd=est_cost,
    )
    db.insert_equity_points(run_id, curve)

    return {
        "entry_id": entry_id,
        "run_id": run_id,
        "cached": False,
        "model": entry.get("model"),
        "model_id": model_id,
        "window": {"start_date": start_date, "end_date": end_date},
        "total_return": metrics["total_return"],
        "sharpe_ratio": metrics["sharpe_ratio"],
        "max_drawdown": metrics["max_drawdown"],
        "final_equity": metrics["final_equity"],
        "num_trades": strategy_impl.num_trades(),
        "llm_calls": llm_calls,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "est_cost_usd": est_cost,
    }


def _rank_entries(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not entries:
        return entries

    by_return = sorted(entries, key=lambda e: e.get("cumulative_return") or 0, reverse=True)
    by_sharpe = sorted(entries, key=lambda e: e.get("sharpe_ratio") or 0, reverse=True)

    rank_cr = {id(e): i + 1 for i, e in enumerate(by_return)}
    rank_sr = {id(e): i + 1 for i, e in enumerate(by_sharpe)}

    for entry in entries:
        entry["rank_cr"] = rank_cr[id(entry)]
        entry["rank_sr"] = rank_sr[id(entry)]
        entry["final_score"] = (entry["rank_cr"] + entry["rank_sr"]) / 2

    entries.sort(key=lambda e: (e["final_score"], -(e.get("cumulative_return") or 0)))
    for idx, entry in enumerate(entries):
        entry["rank"] = idx + 1
    return entries


def get_leaderboard(force_refresh: bool = False) -> Dict[str, Any]:
    """Return ranked leaderboard entries with chart-ready equity curves."""
    meta = ensure_leaderboard_runs(force_refresh=force_refresh)
    config = load_leaderboard_config()
    session_id = config["session_id"]
    start_date = config["start_date"]
    end_date = config["end_date"]
    strategy_by_id = {s["id"]: s for s in config.get("strategies", [])}

    entries: List[Dict[str, Any]] = []
    for strategy in config.get("strategies", []):
        run = _find_cached_run(strategy["id"], start_date, end_date, session_id)
        if not run:
            continue

        equity_hourly = db.get_equity_curve(run["run_id"]) or []
        equity_daily = downsample_daily(equity_hourly)
        strat = strategy_by_id.get(strategy["id"], strategy)
        is_model = strat.get("strategy") == "llm_agent" or strat.get("label") == "Model"

        entries.append(
            {
                "entry_id": strategy["id"],
                "team_name": run["agent_name"],
                "team_badge": strat.get("label", "Baseline"),
                "model": strat.get("model", "Baseline"),
                "entry_type": "baseline",
                "is_model": is_model,
                "initial_equity": run.get("initial_equity") or config.get("initial_capital", INITIAL_CAPITAL),
                "portfolio_value": run.get("final_equity") or config.get("initial_capital", INITIAL_CAPITAL),
                "cumulative_return": run.get("total_return") or 0,
                "sharpe_ratio": run.get("sharpe_ratio") or 0,
                "max_drawdown": run.get("max_drawdown") or 0,
                "status": "Model" if is_model else "Baseline",
                "run_id": run["run_id"],
                "llm_calls": run.get("llm_calls") or 0,
                "input_tokens": run.get("input_tokens") or 0,
                "output_tokens": run.get("output_tokens") or 0,
                "est_cost_usd": run.get("est_cost_usd") or 0,
                "equity_curve": equity_daily,
            }
        )

    entries = _rank_entries(entries)
    leader = entries[0]["team_name"] if entries else "—"

    return {
        "window": {
            "start_date": start_date,
            "end_date": end_date,
            "label": f"{start_date} → {end_date}",
            "description": config.get("description", ""),
        },
        "updated_at": meta.get("refreshed_at"),
        "total_entries": len(entries),
        "leader": leader,
        "entries": entries,
    }
