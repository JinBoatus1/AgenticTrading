"""Leaderboard contest: baseline strategies on a fixed backtest window."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from database import db
from engines.leaderboard_baselines import (
    INITIAL_CAPITAL,
    calc_metrics,
    downsample_daily,
    fetch_hourly_bars,
)
from engines.strategies import get_strategy
from paths import CONFIG_DIR

LEADERBOARD_MODE = "leaderboard"


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

        entries.append(
            {
                "entry_id": strategy["id"],
                "team_name": run["agent_name"],
                "team_badge": strat.get("label", "Baseline"),
                "model": strat.get("model", "Baseline"),
                "entry_type": "baseline",
                "initial_equity": run.get("initial_equity") or config.get("initial_capital", INITIAL_CAPITAL),
                "portfolio_value": run.get("final_equity") or config.get("initial_capital", INITIAL_CAPITAL),
                "cumulative_return": run.get("total_return") or 0,
                "sharpe_ratio": run.get("sharpe_ratio") or 0,
                "max_drawdown": run.get("max_drawdown") or 0,
                "status": "Baseline",
                "run_id": run["run_id"],
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
