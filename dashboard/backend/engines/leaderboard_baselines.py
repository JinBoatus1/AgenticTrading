"""Leaderboard baseline strategy plumbing.

Strategy *logic* lives in the ``engines.strategies`` package — one file per
strategy. This module just handles data fetching, dispatch, and metrics.
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List

import pandas as pd

from engines.strategies import get_strategy
from paths import SCRIPTS_DIR

sys.path.insert(0, str(SCRIPTS_DIR))
import backtest_hourly_agent as bha  # noqa: E402

INITIAL_CAPITAL = bha.INITIAL_CAPITAL


def fetch_hourly_bars(symbols: List[str], start_date: str, end_date: str) -> Dict[str, pd.DataFrame]:
    """Load Alpaca hourly bars for the contest window."""
    loader = bha.AlpacaDataLoader()
    return loader.fetch_bars(symbols, start_date, end_date)


def compute_equity_curve(
    strategy: Dict[str, Any],
    bars_by_symbol: Dict[str, pd.DataFrame],
    start_date: str,
    end_date: str,
    initial_capital: float = INITIAL_CAPITAL,
) -> List[Dict[str, Any]]:
    """Run one leaderboard baseline strategy via the strategy registry."""
    return get_strategy(strategy).run(
        bars_by_symbol, start_date, end_date, initial_capital
    )


def calc_metrics(equity_curve: List[Dict[str, Any]], initial_capital: float) -> Dict[str, float]:
    """Sharpe, drawdown, return from an hourly equity curve."""
    if not equity_curve:
        return {
            "initial_equity": initial_capital,
            "final_equity": initial_capital,
            "total_return": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown": 0.0,
        }

    initial_eq = equity_curve[0].get("equity", initial_capital)
    final_eq = equity_curve[-1].get("equity", initial_capital)
    total_return = (final_eq - initial_capital) / initial_capital if initial_capital else 0.0

    return {
        "initial_equity": float(initial_eq),
        "final_equity": float(final_eq),
        "total_return": float(total_return),
        "sharpe_ratio": float(bha.HourlyBacktester._calc_sharpe(equity_curve)),
        "max_drawdown": float(bha.HourlyBacktester._calc_max_dd(equity_curve)),
    }


def downsample_daily(equity_curve: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep last equity point per calendar day for chart display."""
    by_day: Dict[str, Dict[str, Any]] = {}
    for point in equity_curve:
        ts = str(point.get("timestamp", ""))
        day = ts[:10] if len(ts) >= 10 else ts
        if day:
            by_day[day] = point
    return [by_day[day] for day in sorted(by_day.keys())]
