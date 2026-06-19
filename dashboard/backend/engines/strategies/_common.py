"""Shared, side-effect-free helpers for baseline strategies.

These utilities only build price series and equity curves from already-fetched
bars. They contain no strategy logic, so individual strategies stay independent.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd
import pytz

_ET = pytz.timezone("US/Eastern")


def filter_market_hours(timestamps: List[Any]) -> List[Any]:
    """Keep only regular US market-hours timestamps (9:30–16:00 ET)."""
    kept = []
    for ts in timestamps:
        ts_et = ts.astimezone(_ET)
        hour, minute = ts_et.hour, ts_et.minute
        is_market_hours = (
            (hour > 9 and hour < 16)
            or (hour == 9 and minute >= 30)
            or (hour == 16 and minute == 0)
        )
        if is_market_hours:
            kept.append(ts)
    return kept


def market_timestamps(bars_subset: Dict[str, pd.DataFrame]) -> List[Any]:
    """Sorted, market-hours-only union of timestamps across the given symbols."""
    all_ts = set()
    for df in bars_subset.values():
        all_ts.update(df.index)
    return filter_market_hours(sorted(all_ts))


def build_price_cache(
    bars_subset: Dict[str, pd.DataFrame],
    timestamps: List[Any],
) -> Dict[str, Dict[Any, float]]:
    """Forward-filled close price per symbol over the supplied timestamps."""
    if not timestamps:
        return {}

    first_ts = timestamps[0]
    cache: Dict[str, Dict[Any, float]] = {}
    for symbol, df in bars_subset.items():
        if first_ts not in df.index:
            continue
        last_price = df.loc[first_ts, "close"]
        per_ts: Dict[Any, float] = {}
        for ts in timestamps:
            if ts in df.index:
                last_price = df.loc[ts, "close"]
            per_ts[ts] = last_price
        cache[symbol] = per_ts
    return cache


def equity_curve_from_positions(
    positions: Dict[str, int],
    cash: float,
    price_cache: Dict[str, Dict[Any, float]],
    timestamps: List[Any],
) -> List[Dict[str, Any]]:
    """Build an equity curve given fixed share counts and a price cache."""
    curve: List[Dict[str, Any]] = []
    for ts in timestamps:
        positions_value = 0.0
        for symbol, shares in positions.items():
            prices = price_cache.get(symbol)
            if prices and ts in prices:
                positions_value += shares * prices[ts]
        total_equity = cash + positions_value
        curve.append(
            {
                "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                "equity": round(total_equity, 2),
                "cash": round(cash, 2),
                "positions_value": round(positions_value, 2),
                "daily_return": 0,
            }
        )
    return curve


def subset_bars(
    bars_by_symbol: Dict[str, pd.DataFrame],
    symbols: List[str],
) -> Dict[str, pd.DataFrame]:
    """Return only the bars for symbols that are both requested and available."""
    return {s: bars_by_symbol[s] for s in symbols if s in bars_by_symbol}
