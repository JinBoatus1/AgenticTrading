"""Fetch real market-index levels (e.g. ^DJI, ^GSPC) from Yahoo Finance.

Alpaca only serves tradeable securities (ETFs like DIA/SPY), not the underlying
index. ETFs drift off the index (dividends, NAV premium), so for a true
"market index" baseline we pull the index series directly from Yahoo.
"""

from __future__ import annotations

import datetime as dt
from typing import List, Tuple

import requests

_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
_HEADERS = {"User-Agent": "Mozilla/5.0"}


def _epoch(date_str: str) -> int:
    return int(
        dt.datetime.strptime(date_str, "%Y-%m-%d")
        .replace(tzinfo=dt.timezone.utc)
        .timestamp()
    )


def fetch_index_hourly(
    symbol: str,
    start_date: str,
    end_date: str,
    timeout: int = 20,
) -> List[Tuple[dt.datetime, float]]:
    """Return [(timestamp_utc, close)] hourly index points within [start, end].

    Yahoo's hourly endpoint ignores period2 and returns through the present, so
    results are filtered to the requested window here.
    """
    start_e = _epoch(start_date)
    end_e = _epoch(end_date) + 86400  # inclusive of end_date

    resp = requests.get(
        _CHART_URL.format(symbol=symbol),
        params={"period1": start_e, "period2": end_e, "interval": "1h"},
        headers=_HEADERS,
        timeout=timeout,
    )
    resp.raise_for_status()

    results = (resp.json().get("chart") or {}).get("result") or []
    if not results:
        return []

    res = results[0]
    timestamps = res.get("timestamp") or []
    quote = (res.get("indicators") or {}).get("quote") or [{}]
    closes = quote[0].get("close") or []

    points: List[Tuple[dt.datetime, float]] = []
    for ts, close in zip(timestamps, closes):
        if close is None or not (start_e <= ts < end_e):
            continue
        points.append((dt.datetime.fromtimestamp(ts, dt.timezone.utc), float(close)))
    return points
