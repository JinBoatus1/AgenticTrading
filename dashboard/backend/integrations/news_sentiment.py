"""FinSearch news-sentiment adapter (Plan 1).

Consumers:
- execution/backtest_backend.py::load_news_sentiment  (fail-closed, per-step as_of)
- api/routers/news.py                                  (latest artifact, panel payload)

Contract: docs/integrations/finsearch-news-sentiment.md
"""
from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple, Union

import requests

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://agenticfinsearch.org/api/signals/news/"
_TIMEOUT_SECONDS = 10
_MAX_CACHE_ENTRIES = 64  # bounded — a long-lived server must not grow monotonically

UNAVAILABLE_PAYLOAD = {
    "status": "unavailable", "status_reason": None, "generated_at": None,
    "staleness_hours": None, "news_overview": None, "signals": {}, "feed": [],
}

_lock = threading.Lock()
# key: (as_of or "", tickers_key) -> {"etag": str|None, "body": dict|None}
_CACHE: Dict[Tuple[str, str], Dict[str, Any]] = {}


def clear_cache() -> None:
    with _lock:
        _CACHE.clear()


def _base_url() -> str:
    return os.environ.get("FINSEARCH_SIGNALS_URL", DEFAULT_BASE_URL)


def _headers() -> Dict[str, str]:
    key = os.environ.get("FINGPT_API_KEY", "")
    return {"Authorization": f"Bearer {key}"} if key else {}


def _http_get(*, params: Dict[str, str], headers: Dict[str, str]):
    return requests.get(_base_url(), params=params, headers=headers,
                        timeout=_TIMEOUT_SECONDS)


def _coerce_timestamp(timestamp: Union[str, datetime, None]) -> Optional[datetime]:
    """The v2 step envelope serializes timestamps to ISO strings
    (external_run_service.py:429-431), so the REAL backtest call site passes
    str; direct callers may pass datetime. Returns tz-aware datetime or None."""
    if timestamp is None:
        return None
    if isinstance(timestamp, str):
        try:
            timestamp = datetime.fromisoformat(timestamp)
        except ValueError:
            logger.error("news_sentiment: unparseable timestamp %r", timestamp)
            return None
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp


def fetch_signals(*, as_of: Optional[str], tickers: Tuple[str, ...]) -> Optional[dict]:
    """Fetch one signals artifact; None on any failure (fail closed, log loud).

    Memo policy: keys dated STRICTLY BEFORE today (UTC) are served from the
    memo without HTTP once any result — including a config-error None — is
    cached (past days are immutable for our purposes, and a 401 must not turn
    a 161-step backtest into 161 live calls). Keys for today, and the
    `as_of=None` "latest" read, always revalidate (ETag/If-None-Match), so a
    404 seen before the daily heartbeat lands never sticks. A transport
    failure NEVER serves a cached body — stale data presented as fresh is
    worse than an honest gap.
    """
    key = (as_of or "", ",".join(tickers))
    today = datetime.now(timezone.utc).date().isoformat()
    with _lock:
        cached = _CACHE.get(key)
    if cached is not None and as_of and as_of < today:  # ISO dates sort lexically
        return cached["body"]
    params: Dict[str, str] = {}
    if as_of:
        params["as_of"] = as_of
    if tickers:
        params["tickers"] = ",".join(tickers)
    headers = _headers()
    if cached and cached.get("etag"):
        headers["If-None-Match"] = cached["etag"]
    try:
        resp = _http_get(params=params, headers=headers)
    except Exception as exc:  # network/timeout: fail closed, never stale
        logger.warning("news_sentiment: fetch failed: %s", exc)
        return None
    if resp.status_code == 304 and cached:
        return cached["body"]
    body: Optional[dict] = None
    if resp.status_code == 200:
        try:
            body = resp.json()
        except ValueError:
            logger.error("news_sentiment: unparseable producer body")
        else:
            if body.get("status") == "degraded":
                logger.warning("news_sentiment: degraded artifact: %s",
                               body.get("status_reason"))
    elif resp.status_code == 401:
        logger.error("news_sentiment: 401 from producer — missing/wrong FINGPT_API_KEY")
    elif resp.status_code == 503:
        logger.error("news_sentiment: 503 — producer auth misconfigured server-side")
    elif resp.status_code == 400:
        logger.error("news_sentiment: 400 bad_as_of — adapter bug (as_of=%r)", as_of)
    elif resp.status_code == 404:
        pass  # no artifact at/before as_of: normal for early steps
    else:
        logger.warning("news_sentiment: unexpected status %s", resp.status_code)
    with _lock:
        _CACHE[key] = {"etag": resp.headers.get("ETag"), "body": body}
        while len(_CACHE) > _MAX_CACHE_ENTRIES:
            _CACHE.pop(next(iter(_CACHE)))  # evict oldest-inserted
    return body


def _project_entry(sig: dict, reference_ts: float) -> dict:
    return {
        "sentiment": sig["sentiment"],
        "score": sig["score"],
        "headline": sig["headline"],
        "source": sig["source"],
        "url": sig["url"],
        "n_articles": sig["n_articles"],
        "age_hours": max(0.0, (reference_ts - float(sig["published"])) / 3600.0),
        "rationale": sig.get("rationale"),
    }


def get_news_sentiment(universe, timestamp) -> dict:
    """Contract interface for execution/backtest_backend.load_news_sentiment."""
    empty = {"news_sentiment": {}, "news_overview": None}
    ts = _coerce_timestamp(timestamp)
    if ts is None:
        return empty
    as_of = ts.date().isoformat()
    reference_ts = ts.timestamp()
    tickers = tuple(sorted(universe or ()))
    body = fetch_signals(as_of=as_of, tickers=tickers)
    if not body:
        return empty
    wanted = set(tickers)
    out = {
        sym: _project_entry(sig, reference_ts)
        for sym, sig in (body.get("signals") or {}).items()
        if not wanted or sym in wanted
    }
    return {"news_sentiment": out, "news_overview": body.get("news_overview")}


def get_latest_panel_payload(tickers) -> dict:
    """Latest-artifact read for the Home panel (no as_of).

    `feed` is served backend-side even though Phase A derives it from
    `signals`, so the wire format (and the frontend) do not change when
    Phase B swaps the feed source to the raw-items endpoint."""
    body = fetch_signals(as_of=None, tickers=tuple(sorted(tickers or ())))
    if not body:
        return dict(UNAVAILABLE_PAYLOAD)
    signals = body.get("signals") or {}
    feed = sorted(
        (
            {
                "headline": s["headline"], "source": s["source"], "url": s["url"],
                "published": s["published"], "ticker": sym,
            }
            for sym, s in signals.items()
        ),
        key=lambda item: item["published"], reverse=True,
    )
    return {
        "status": body.get("status", "ok"),
        "status_reason": body.get("status_reason"),
        "generated_at": body.get("generated_at"),
        "staleness_hours": body.get("staleness_hours"),
        "news_overview": body.get("news_overview"),
        "signals": signals,
        "feed": feed,
    }
