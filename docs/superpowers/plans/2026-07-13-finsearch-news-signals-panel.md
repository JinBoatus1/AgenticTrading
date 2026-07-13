# FinSearch News & Signals — Adapter + Home Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the FinSearch news-sentiment adapter (`integrations/news_sentiment.py`), a cached `/api/news/signals` proxy, and a Home-view panel showing the latest news feed (left) and identified signals (right).

**Architecture:** One adapter module with a shared HTTP core serves two consumers: the fail-closed backtest loader (`execution/backtest_backend.py`, `?as_of` stepping) and a new panel proxy router (latest artifact, 420s TTL cache). The browser never talks to FinSearch — the bearer key stays server-side. Phase A powers the feed from the signals artifact's representative stories; Phase B (cross-repo) adds a FinSearch raw-items endpoint and upgrades the feed.

**Tech Stack:** FastAPI router + Pydantic (ATL), `requests==2.33.1` (already pinned), vanilla JS + existing Home lifecycle hooks (no build step), Django view (FinSearch, Phase B).

**Spec:** `docs/superpowers/specs/2026-07-13-finsearch-news-signals-panel-design.md`. Normative producer contract: `docs/integrations/finsearch-news-sentiment.md`.

## Global Constraints

- Repo root on `sys.path`; run everything from the repo root; tests via `pytest dashboard/backend/tests/ -v`.
- `domain/` must not import `api/`/`app.py`; the new `integrations/news_sentiment.py` must not import `api/` or `execution/` (it is imported BY them).
- Every new route requires updating `tests/test_app_composition.py::EXPECTED_FULL_CONTRACT` AND a golden set following `tests/test_router_move.py` conventions, in the same commit — otherwise CI goes red on every open PR.
- All adapter tests are offline (fixture-driven); no test may hit the network or require `FINGPT_API_KEY`.
- `age_hours` is always computed against the passed `timestamp`, never `datetime.now()`.
- **The v2 step envelope carries `timestamp` as an ISO-8601 STRING** (`external_run_service.py:429-431` serializes it; the existing tests at `test_execution_backends.py:30,90` pass string literals). The adapter must accept `str | datetime`; assuming datetime makes the feature silently no-op behind the fail-closed loader.
- Frontend: no framework, no build step; follow `API.get`/`AbortController`/destroy-recreate conventions in `app.js`.

---

### Task 1: Add optional `rationale` to `NewsSentimentEntry`

**Files:**
- Modify: `dashboard/backend/api/v2/models.py:19-26` (the `NewsSentimentEntry` class)
- Modify: `docs/integrations/finsearch-news-sentiment.md` (the projection table row "`rationale`, `guid` | dropped" and the "Design note — rationale" section become stale the moment this merges — update both to record that `rationale` now has a slot; `guid` remains dropped)
- Test: `dashboard/backend/tests/test_v2_contracts.py`

**Interfaces:**
- Produces: `NewsSentimentEntry.rationale: str | None = None` — later tasks project the producer's `rationale` into this slot.

- [ ] **Step 1: Write the failing tests**

```python
# append to dashboard/backend/tests/test_v2_contracts.py
def test_news_sentiment_entry_accepts_rationale():
    entry = NewsSentimentEntry(
        sentiment="bullish", score=0.5, headline="h", source="s",
        url="https://example.com", age_hours=1.0, n_articles=2,
        rationale="Two outlets report upbeat guidance.",
    )
    assert entry.rationale == "Two outlets report upbeat guidance."


def test_news_sentiment_entry_rationale_is_optional():
    entry = NewsSentimentEntry(
        sentiment="neutral", score=0.0, headline="h", source="s",
        url="https://example.com", age_hours=0.0, n_articles=1,
    )
    assert entry.rationale is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest dashboard/backend/tests/test_v2_contracts.py -v -k rationale`
Expected: FAIL — `ValidationError`/`TypeError` (unknown field `rationale`).

- [ ] **Step 3: Add the field**

```python
# in NewsSentimentEntry (api/v2/models.py), after n_articles:
    rationale: Optional[str] = None  # producer's one-line directional reasoning (additive, 2026-07-13)
```

- [ ] **Step 4: Run the full v2 contract file**

Run: `pytest dashboard/backend/tests/test_v2_contracts.py -v`
Expected: PASS (all — additive change must not break existing envelope tests).

- [ ] **Step 5: Commit**

```bash
git add dashboard/backend/api/v2/models.py dashboard/backend/tests/test_v2_contracts.py
git commit -m "feat(v2): additive optional rationale on NewsSentimentEntry"
```

---

### Task 2: Vendor the producer fixture + schema for offline tests

**Files:**
- Create: `dashboard/backend/tests/fixtures/signals-v1.schema.json` (copy from FinSearch `Heartbeat/schemas/signals-v1.schema.json`)
- Create: `dashboard/backend/tests/fixtures/signals-fixture.json` (copy from FinSearch `Heartbeat/tests/fixtures/signals-fixture.json`)
- Test: `dashboard/backend/tests/test_news_sentiment_fixture.py`

**Interfaces:**
- Produces: fixture paths used by Tasks 3–6's tests; helper `load_signals_fixture() -> dict`.

- [ ] **Step 1: Copy both files verbatim** from `/mnt/d/FinGPT/Github/fingpt_rcos/Heartbeat/{schemas/signals-v1.schema.json,tests/fixtures/signals-fixture.json}` (or the FinSearch repo's current main). Do not edit them — they are the producer's contract artifacts.

- [ ] **Step 2: Write a fixture sanity test**

```python
# dashboard/backend/tests/test_news_sentiment_fixture.py
import json
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def load_signals_fixture() -> dict:
    return json.loads((FIXTURES / "signals-fixture.json").read_text())


def test_fixture_matches_contract_essentials():
    body = load_signals_fixture()
    assert body["schema_version"] == 1
    assert isinstance(body["signals"], dict) and body["signals"]
    sample = next(iter(body["signals"].values()))
    for field in ("sentiment", "score", "rationale", "headline", "source",
                  "url", "published", "guid", "n_articles"):
        assert field in sample
```

- [ ] **Step 3: Run it**

Run: `pytest dashboard/backend/tests/test_news_sentiment_fixture.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add dashboard/backend/tests/fixtures/ dashboard/backend/tests/test_news_sentiment_fixture.py
git commit -m "test: vendor signals-v1 schema + fixture for offline adapter tests"
```

---

### Task 3: Adapter module — HTTP core + backtest projection

**Files:**
- Create: `dashboard/backend/integrations/news_sentiment.py`
- Test: `dashboard/backend/tests/test_news_sentiment_adapter.py`

**Interfaces:**
- Consumes: fixture helper from Task 2.
- Produces:
  - `fetch_signals(*, as_of: str | None, tickers: tuple[str, ...]) -> dict | None`
  - `get_news_sentiment(universe: list[str], timestamp) -> dict` — the exact interface `execution/backtest_backend.py:33-40` already imports; returns `{"news_sentiment": {sym: entry_dict}, "news_overview": str | None}` where `entry_dict` includes `rationale`.
  - `get_latest_panel_payload(tickers: list[str]) -> dict` (Task 4 fills the feed; declared here).
  - Module-level `_CACHE` memo, `clear_cache()` for tests.

- [ ] **Step 1: Write the failing tests** (representative set — all offline via `monkeypatch`):

```python
# dashboard/backend/tests/test_news_sentiment_adapter.py
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from dashboard.backend.integrations import news_sentiment as ns
from dashboard.backend.tests.test_news_sentiment_fixture import load_signals_fixture


@pytest.fixture(autouse=True)
def _clean():
    ns.clear_cache()
    yield
    ns.clear_cache()


def _fake_response(status=200, body=None, etag='"e1"'):
    return SimpleNamespace(
        status_code=status,
        headers={"ETag": etag},
        json=lambda: body if body is not None else load_signals_fixture(),
    )


def test_projection_maps_all_fields_including_rationale(monkeypatch):
    body = load_signals_fixture()
    monkeypatch.setattr(ns, "_http_get", lambda **kw: _fake_response(body=body))
    ts = datetime(2026, 7, 10, 15, 0, tzinfo=timezone.utc)
    out = ns.get_news_sentiment(["MSFT", "AAPL"], ts)
    sym, src = next(iter(body["signals"].items()))
    entry = out["news_sentiment"].get(sym)
    if entry is not None:  # fixture symbol may not be in the passed universe filter
        assert entry["sentiment"] == src["sentiment"]
        assert entry["rationale"] == src["rationale"]
        assert entry["age_hours"] >= 0.0
    assert out["news_overview"] == body["news_overview"]


def test_age_hours_referenced_to_step_timestamp_not_wallclock(monkeypatch):
    body = load_signals_fixture()
    sym = next(iter(body["signals"]))
    published = body["signals"][sym]["published"]
    step_ts = datetime.fromtimestamp(published + 7200, tz=timezone.utc)  # 2h later
    monkeypatch.setattr(ns, "_http_get", lambda **kw: _fake_response(body=body))
    out = ns.get_news_sentiment([sym], step_ts)
    assert abs(out["news_sentiment"][sym]["age_hours"] - 2.0) < 0.01


def test_404_is_quiet_empty(monkeypatch):
    monkeypatch.setattr(ns, "_http_get", lambda **kw: _fake_response(status=404, body={}))
    out = ns.get_news_sentiment(["MSFT"], datetime.now(timezone.utc))
    assert out == {"news_sentiment": {}, "news_overview": None}


def test_401_is_empty_and_logs_error(monkeypatch, caplog):
    monkeypatch.setattr(ns, "_http_get", lambda **kw: _fake_response(status=401, body={}))
    with caplog.at_level("ERROR"):
        out = ns.get_news_sentiment(["MSFT"], datetime.now(timezone.utc))
    assert out["news_sentiment"] == {}
    assert any("FINGPT_API_KEY" in r.message for r in caplog.records)


def test_network_error_fails_closed_never_stale(monkeypatch):
    """A transport failure returns unavailable — it must NOT serve the
    previously cached body for the same key (stale data presented as fresh
    during an outage)."""
    body = load_signals_fixture()
    monkeypatch.setattr(ns, "_http_get", lambda **kw: _fake_response(body=body))
    warm = ns.get_latest_panel_payload(["MSFT"])  # warms the ("", tickers) key
    assert warm["status"] != "unavailable"

    def _boom(**kw):
        raise OSError("connection refused")
    monkeypatch.setattr(ns, "_http_get", _boom)
    out = ns.get_latest_panel_payload(["MSFT"])  # same key, latest path revalidates
    assert out["status"] == "unavailable"


def test_real_call_site_passes_iso_string(monkeypatch):
    """The v2 step envelope serializes timestamp to an ISO STRING
    (external_run_service.py:429-431) — the adapter must parse it, not crash
    into the fail-closed loader."""
    body = load_signals_fixture()
    monkeypatch.setattr(ns, "_http_get", lambda **kw: _fake_response(body=body))
    out = ns.get_news_sentiment(["MSFT"], "2026-07-10T15:00:00+00:00")
    assert out["news_overview"] == body["news_overview"]  # parsed, not swallowed


def test_garbage_timestamp_fails_closed(monkeypatch):
    monkeypatch.setattr(ns, "_http_get", lambda **kw: _fake_response())
    out = ns.get_news_sentiment(["MSFT"], "not-a-date")
    assert out == {"news_sentiment": {}, "news_overview": None}


def test_past_as_of_memoized_one_call(monkeypatch):
    calls = []
    def _counting(**kw):
        calls.append(kw)
        return _fake_response()
    monkeypatch.setattr(ns, "_http_get", _counting)
    ts = datetime(2026, 7, 10, 15, 0, tzinfo=timezone.utc)  # strictly past date
    ns.get_news_sentiment(["MSFT"], ts)
    ns.get_news_sentiment(["MSFT"], ts.replace(hour=16))  # same date -> same as_of
    assert len(calls) == 1


def test_config_error_negative_cached_for_past_dates(monkeypatch):
    """A 401 must not turn a 161-step backtest into 161 live calls."""
    calls = []
    def _unauth(**kw):
        calls.append(1)
        return _fake_response(status=401, body={})
    monkeypatch.setattr(ns, "_http_get", _unauth)
    ts = datetime(2026, 7, 1, 15, 0, tzinfo=timezone.utc)
    ns.get_news_sentiment(["MSFT"], ts)
    ns.get_news_sentiment(["MSFT"], ts)
    assert len(calls) == 1


def test_todays_404_not_hard_memoized(monkeypatch):
    """A 404 seen before the daily heartbeat lands must not stick for the
    process lifetime — today's key always revalidates."""
    responses = [_fake_response(status=404, body={}), _fake_response()]
    monkeypatch.setattr(ns, "_http_get", lambda **kw: responses.pop(0))
    now = datetime.now(timezone.utc)
    first = ns.get_news_sentiment(["MSFT"], now)
    second = ns.get_news_sentiment(["MSFT"], now)
    assert first["news_sentiment"] == {}
    assert second["news_overview"] is not None
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest dashboard/backend/tests/test_news_sentiment_adapter.py -v`
Expected: FAIL — `ModuleNotFoundError: dashboard.backend.integrations.news_sentiment`.

- [ ] **Step 3: Implement the module**

```python
# dashboard/backend/integrations/news_sentiment.py
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
```

- [ ] **Step 4: Run the adapter tests**

Run: `pytest dashboard/backend/tests/test_news_sentiment_adapter.py dashboard/backend/tests/test_execution_backends.py -v`
Expected: PASS — but `test_execution_backends.py::test_news_sentiment_fail_closed_when_plan1_absent` (:28-40) **must be updated in this task**. It currently passes because the module doesn't exist; once it exists, the test's premise is false and — worse — it calls `load_news_sentiment` with the REAL module, which would issue a live HTTP request from CI. Update it to simulate absence explicitly so the absent-module path stays genuinely covered and no network is touched:

```python
def test_news_sentiment_fail_closed_when_plan1_absent(monkeypatch):
    """Module absent -> loader degrades to ({}, None). Simulated absence:
    a None entry in sys.modules makes the in-function import raise ImportError."""
    import sys
    monkeypatch.setitem(sys.modules,
                        "dashboard.backend.integrations.news_sentiment", None)
    sentiment, overview = load_news_sentiment(["AAPL"], "2026-04-15T10:30:00+00:00")
    assert sentiment == {}
    assert overview is None
```

The raising-loader variant (`:78-90`) stays as is.

- [ ] **Step 5: Commit**

```bash
git add dashboard/backend/integrations/news_sentiment.py dashboard/backend/tests/test_news_sentiment_adapter.py
git commit -m "feat(integrations): FinSearch news-sentiment adapter (fail-closed, as_of, ETag memo)"
```

---

### Task 4: Panel payload — `get_latest_panel_payload`

**Files:**
- Modify: `dashboard/backend/integrations/news_sentiment.py`
- Test: `dashboard/backend/tests/test_news_sentiment_adapter.py`

**Interfaces:**
- Produces: `get_latest_panel_payload(tickers: list[str]) -> dict` with keys
  `status` (`"ok" | "degraded" | "unavailable"`), `status_reason`, `generated_at`,
  `staleness_hours`, `news_overview`, `signals` (dict, per-ticker incl. `rationale`, `published`),
  `feed` (list of `{headline, source, url, published, ticker}` sorted by `published` desc).

- [ ] **Step 1: Write the failing tests**

```python
def test_panel_payload_shapes_feed_and_signals(monkeypatch):
    body = load_signals_fixture()
    monkeypatch.setattr(ns, "_http_get", lambda **kw: _fake_response(body=body))
    payload = ns.get_latest_panel_payload(["MSFT", "AAPL"])
    assert payload["status"] in ("ok", "degraded")
    assert payload["news_overview"] == body["news_overview"]
    assert set(payload["signals"]) <= set(body["signals"])
    pubs = [item["published"] for item in payload["feed"]]
    assert pubs == sorted(pubs, reverse=True)
    for item in payload["feed"]:
        assert item["url"] and item["headline"] and item["source"]


def test_panel_payload_unavailable_on_failure(monkeypatch):
    def _boom(**kw):
        raise OSError("down")
    monkeypatch.setattr(ns, "_http_get", _boom)
    payload = ns.get_latest_panel_payload(["MSFT"])
    assert payload == ns.UNAVAILABLE_PAYLOAD  # single-sourced shape (router reuses it)
```

- [ ] **Step 2: Run to verify failure** — `pytest ... -k panel_payload -v` → FAIL (`AttributeError`).

- [ ] **Step 3: Implement**

```python
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
```

- [ ] **Step 4: Run** — `pytest dashboard/backend/tests/test_news_sentiment_adapter.py -v` → PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(integrations): latest-artifact panel payload"` (with both files staged).

---

### Task 5: Panel proxy route `/api/news/signals` + cache + contract freezes

**Files:**
- Create: `dashboard/backend/api/routers/news.py`
- Modify: `dashboard/backend/api/router.py` (mount after `strategies_router`, `router.py:25`)
- Modify: `dashboard/backend/cache.py` — beside the existing constants at `cache.py:83-94` add: `shared_ttl_cache = paper_trading_cache` (alias with a comment: the class is a generic TTL cache; paper trading was merely its first consumer — new non-paper consumers use this name), `CACHE_KEY_NEWS_SIGNALS = "news:signals"` (namespaced like the `paper:` keys), `TTL_NEWS = 420` (**deliberately above** the frontend's 300s poll so a client's own re-poll lands inside the cached window instead of always missing at the boundary)
- Modify: `dashboard/backend/tests/test_app_composition.py` (`EXPECTED_FULL_CONTRACT`: add `("GET", "/api/news/signals")`)
- Modify: `dashboard/backend/tests/test_router_move.py` (add `EXPECTED_NEWS_ROUTES` golden set + `test_news_router_route_contract_unchanged`, following the existing pattern at `test_router_move.py:33-107,153-154`)
- Test: `dashboard/backend/tests/test_news_router.py`

**Interfaces:**
- Consumes: `get_latest_panel_payload` (Task 4), `paper_trading_cache` (`cache.py:79`), `DJIA_30` (`infrastructure/llm/validator.py`).
- Produces: `GET /api/news/signals` → panel payload JSON (always 200).

- [ ] **Step 1: Write the failing tests**

```python
# dashboard/backend/tests/test_news_router.py
from fastapi.testclient import TestClient

from dashboard.backend.app import app
from dashboard.backend import cache as cache_mod
from dashboard.backend.integrations import news_sentiment as ns


def test_news_signals_route_returns_payload(monkeypatch):
    cache_mod.shared_ttl_cache.invalidate(cache_mod.CACHE_KEY_NEWS_SIGNALS)
    fake = {"status": "ok", "status_reason": None, "generated_at": "2026-07-13T11:20:00+00:00",
            "staleness_hours": 1.2, "news_overview": "calm", "signals": {}, "feed": []}
    monkeypatch.setattr(ns, "get_latest_panel_payload", lambda tickers: fake)
    client = TestClient(app)
    resp = client.get("/api/news/signals")
    assert resp.status_code == 200
    assert resp.json()["news_overview"] == "calm"


def test_news_signals_route_fail_closed(monkeypatch):
    cache_mod.shared_ttl_cache.invalidate(cache_mod.CACHE_KEY_NEWS_SIGNALS)
    def _boom(tickers):
        raise RuntimeError("adapter exploded")
    monkeypatch.setattr(ns, "get_latest_panel_payload", _boom)
    client = TestClient(app)
    resp = client.get("/api/news/signals")
    assert resp.status_code == 200
    assert resp.json()["status"] == "unavailable"


def test_news_signals_route_caches(monkeypatch):
    cache_mod.shared_ttl_cache.invalidate(cache_mod.CACHE_KEY_NEWS_SIGNALS)
    calls = []
    def _once(tickers):
        calls.append(1)
        return {"status": "ok", "status_reason": None, "generated_at": None,
                "staleness_hours": None, "news_overview": None, "signals": {}, "feed": []}
    monkeypatch.setattr(ns, "get_latest_panel_payload", _once)
    client = TestClient(app)
    client.get("/api/news/signals")
    client.get("/api/news/signals")
    assert len(calls) == 1
```

- [ ] **Step 2: Run to verify failure** — 404 on `/api/news/signals`.

- [ ] **Step 3: Implement the router**

```python
# dashboard/backend/api/routers/news.py
"""Panel proxy for FinSearch news signals — keeps FINGPT_API_KEY server-side."""
import threading

from fastapi import APIRouter

from dashboard.backend.cache import (CACHE_KEY_NEWS_SIGNALS, TTL_NEWS,
                                     shared_ttl_cache)
from dashboard.backend.infrastructure.llm.validator import DJIA_30
from dashboard.backend.integrations import news_sentiment

router = APIRouter(prefix="/news", tags=["news"])

# Single-flight: concurrent cold-cache requests share one upstream fetch
# instead of stampeding the bearer-gated producer at every TTL boundary.
_fetch_lock = threading.Lock()


# Deliberately sync `def`: FastAPI runs it in the threadpool, so the blocking
# requests.get inside the adapter cannot stall the event loop. Do NOT convert
# to `async def` without moving the HTTP call off the loop.
@router.get("/signals")
def latest_news_signals():
    cached = shared_ttl_cache.get(CACHE_KEY_NEWS_SIGNALS)
    if cached is not None:
        return cached
    with _fetch_lock:
        cached = shared_ttl_cache.get(CACHE_KEY_NEWS_SIGNALS)  # re-check after the wait
        if cached is not None:
            return cached
        try:
            payload = news_sentiment.get_latest_panel_payload(list(DJIA_30))
        except Exception:
            return dict(news_sentiment.UNAVAILABLE_PAYLOAD)
        shared_ttl_cache.set(CACHE_KEY_NEWS_SIGNALS, payload, ttl_seconds=TTL_NEWS)
    return payload
```

Mount in `api/router.py` (import + `api_router.include_router(news_router)` alongside `router.py:16-26`), add the two cache constants, and update BOTH contract-freeze tests.

- [ ] **Step 4: Run the route tests + both freeze suites**

Run: `pytest dashboard/backend/tests/test_news_router.py dashboard/backend/tests/test_app_composition.py dashboard/backend/tests/test_router_move.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dashboard/backend/api/routers/news.py dashboard/backend/api/router.py dashboard/backend/cache.py \
        dashboard/backend/tests/test_news_router.py dashboard/backend/tests/test_app_composition.py \
        dashboard/backend/tests/test_router_move.py
git commit -m "feat(api): /api/news/signals panel proxy with TTL cache + contract freezes"
```

---

### Task 6: Home panel frontend

**Files:**
- Modify: `dashboard/frontend/app.html` (new section inside `#homeView`, after the `.home-dashboard-grid` section that ends near `app.html:472`; new `<script src="home-news-signals.js">` beside `app.html:1507-1510`)
- Create: `dashboard/frontend/home-news-signals.js`
- Modify: `dashboard/frontend/home-page.js` (call `newsSignalsPanel.onShow()` / `.onHide()` from `onHomePageShow`/`onHomePageHide`, `home-page.js:648-656`)
- Modify: `dashboard/frontend/styles.css` (panel styles, following `.home-dash-card` family at `styles.css:4359-4368`)

**Interfaces:**
- Consumes: `GET {API_BASE}/api/news/signals` (Task 5 payload), `API_BASE` + `API.get` conventions (`app.js:920-989`).
- Produces: `window.newsSignalsPanel = { onShow(), onHide() }`.

- [ ] **Step 1: Add the markup** (inside `#homeView`, full-width section):

```html
<section class="home-news-signals" id="homeNewsSignals" aria-label="News and signals">
  <div class="home-section-title-row">
    <h2 class="home-section-title">News &amp; Signals <span class="nns-source-tag">via Agentic FinSearch</span></h2>
    <span class="nns-updated" id="nnsUpdated"></span>
    <span class="nns-badge" id="nnsStatusBadge" hidden></span>
  </div>
  <p class="nns-overview" id="nnsOverview"></p>
  <div class="nns-split">
    <!-- Phase A honesty: the left column is the stories BEHIND today's signals
         (one representative story per signalled ticker), not the full fetched
         feed — Phase B renames this heading to "Latest news" when the
         raw-items endpoint powers it. -->
    <div class="nns-col" id="nnsFeed"><h3>Today's signal stories</h3><ul class="nns-list" id="nnsFeedList"></ul></div>
    <div class="nns-col" id="nnsSignals"><h3>Signals</h3><ul class="nns-list" id="nnsSignalsList"></ul></div>
  </div>
</section>
```

- [ ] **Step 2: Implement `home-news-signals.js`**

```javascript
// Home panel: FinSearch signal stories (left) + identified signals (right).
// Data: GET /api/news/signals (server-side proxy; 420s TTL — above this 300s
// poll, so a re-poll lands in-cache). Poll only while the Home view is visible.
// Reuses app.js globals: escapeHtml (attribute-safe), API (fetch wrapper),
// API_BASE; and market-events/marketEventRelativeTime.js for relative times.
// Load order: this script tag must come after app.js and market-events/*.
(function () {
  const POLL_MS = 5 * 60 * 1000;
  let timer = null;

  function relTime(publishedEpochSeconds) {
    // Shared helper takes ms/Date-parseable input; producer sends epoch seconds.
    return window.formatMarketEventRelativeTime
      ? window.formatMarketEventRelativeTime(publishedEpochSeconds * 1000, new Date())
      : '';
  }

  function render(payload) {
    const updated = document.getElementById('nnsUpdated');
    const badge = document.getElementById('nnsStatusBadge');
    const overview = document.getElementById('nnsOverview');
    const feedList = document.getElementById('nnsFeedList');
    const sigList = document.getElementById('nnsSignalsList');
    if (!feedList || !sigList) return;

    if (payload.status === 'unavailable') {
      overview.textContent = 'News signals are currently unavailable.';
      feedList.innerHTML = sigList.innerHTML = '';
      updated.textContent = '';
      badge.hidden = true;
      return;
    }
    updated.textContent = payload.staleness_hours != null
      ? `Updated ${payload.staleness_hours.toFixed(1)}h ago` : '';
    badge.hidden = payload.status !== 'degraded';
    if (!badge.hidden) badge.textContent = `degraded: ${payload.status_reason || 'partial data'}`;
    overview.textContent = payload.news_overview || '';

    feedList.innerHTML = (payload.feed || []).map(item => `
      <li class="nns-item">
        <a href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(item.headline)}</a>
        <span class="nns-meta">${escapeHtml(item.source)} · ${escapeHtml(item.ticker)} · ${relTime(item.published)}</span>
      </li>`).join('') || '<li class="nns-empty">No qualifying news today.</li>';

    sigList.innerHTML = Object.entries(payload.signals || {}).map(([sym, s]) => `
      <li class="nns-item nns-signal nns-${escapeHtml(s.sentiment)}">
        <span class="nns-chip">${escapeHtml(s.sentiment)}</span>
        <strong>${escapeHtml(sym)}</strong> <span class="nns-score">${Number(s.score).toFixed(2)}</span>
        <span class="nns-rationale">${escapeHtml(s.rationale || '')}</span>
        <a class="nns-src" href="${escapeHtml(s.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(s.source)}</a>
      </li>`).join('') || '<li class="nns-empty">No directional reads.</li>';
  }

  async function load() {
    try {
      render(await API.get(`${API_BASE}/api/news/signals`));
    } catch (e) {
      render({ status: 'unavailable' });
    }
  }

  window.newsSignalsPanel = {
    onShow() { load(); if (!timer) timer = setInterval(load, POLL_MS); },
    onHide() { if (timer) { clearInterval(timer); timer = null; } },
  };
})();
```

- [ ] **Step 3: Wire lifecycle + styles.** In `home-page.js` `onHomePageShow`/`onHomePageHide` add `window.newsSignalsPanel && window.newsSignalsPanel.onShow()` / `.onHide()`. Add `.home-news-signals` styles: card chrome matching `.home-dash-card`, `.nns-split { display:grid; grid-template-columns: 1fr 1fr; gap:12px; }` collapsing to one column at the same breakpoint the dash grid uses (`styles.css:4633`), sentiment chip colors for `.nns-bullish/.nns-bearish/.nns-neutral` consistent with existing badge styling.

- [ ] **Step 4: Verify in the running app.** `uvicorn dashboard.backend.app:app --reload`; open `http://localhost:8000/app`. With no `FINGPT_API_KEY` set the panel must show the unavailable state (not an error). Then set `FINSEARCH_SIGNALS_URL` to a local fixture server (`python3 -m http.server` serving the fixture — or temporarily monkeypatch) OR set the real key, and confirm: feed rows link out, signals show chips + rationale, staleness renders, hiding the Home tab stops polling (no network entries in devtools).

- [ ] **Step 5: Commit**

```bash
git add dashboard/frontend/app.html dashboard/frontend/home-news-signals.js dashboard/frontend/home-page.js dashboard/frontend/styles.css
git commit -m "feat(frontend): Home news & signals panel (feed left, signals right)"
```

---

### Task 7: Env plumbing + user-facing docs

**Files:**
- Modify: `.env.example` (repo root — add `FINGPT_API_KEY=` and `FINSEARCH_SIGNALS_URL=` with one-line comments)
- Modify: `README.md:113` (Future Roadmap "Sentiment analysis (Reddit, news APIs)" line — now partially shipped; reword to reflect the live FinSearch signal integration)
- Ops (manual, Felix or maintainer): add `FINGPT_API_KEY` secret to ATL's Render env (same value as the FinSearch backend key).

- [ ] **Step 1: Edit `.env.example` + README; grep the docs** (`docs/source/`) for other stale claims: `grep -rn "sentiment\|news" docs/source/ README.md | grep -iv finsearch` and fix what the panel makes stale.
- [ ] **Step 2: Run the full suite** — `pytest dashboard/backend/tests/ -v` → green.
- [ ] **Step 3: Commit** — `git commit -m "docs+env: FinSearch news integration knobs and roadmap update"`.

---

### Task 8 (Phase B, cross-repo): FinSearch raw-items endpoint + ATL feed upgrade

**Repo: Agentic-FinSearch** (own PR + review cycle there; reference this plan in the PR body). Then a small ATL follow-up PR.

**Files (FinSearch):**
- Modify: `Main/backend/api/signals_views.py` (add `news_items` view — sibling of `news_signals`, same `@require_bearer_auth`/`@ratelimit`/`@condition` idioms)
- Modify: `Main/backend/django_config/urls.py:26` area (add `path("api/news/items/", ...)`)
- Modify: settings (new `RAW_ITEMS_DIR` env-backed setting pointing at the Heartbeat `digests/` dir)
- Test: `Main/backend/tests/test_news_items_endpoint.py` (mirror `test_signals_endpoint.py`: auth 401, newest-batch selection, `limit`, empty→404, conditional GET)

**Behavior:** serve the newest `items-*.jsonl` batch (fields `guid,title,link,source,published,description,tickers,score`), validation-gated (reuse `news_signals.validation_gate` semantics: parse, required fields, published-sanity, text caps) but NOT subject/roundup-gated; `?limit=` (default 50, max 200), newest-first by `published`.

**Files (ATL follow-up):**
- Modify: `dashboard/backend/integrations/news_sentiment.py` — `get_latest_panel_payload` fetches `/api/news/items/` first for `feed`; on any failure falls back to the Phase-A representative-story feed (fail-closed chain).
- Test: extend `test_news_sentiment_adapter.py` with the fallback case.

- [ ] **Step 1 (FinSearch): TDD the view** per the mirror tests above; deploy via the normal FinSearch backend pipeline.
- [ ] **Step 2 (ATL): TDD the feed upgrade** + fallback.
- [ ] **Step 3: Verify end-to-end** — panel left column shows multi-story feed; kill the items endpoint (wrong URL env) and confirm graceful fallback to representative stories.

---

## Verification (whole plan)

1. `pytest dashboard/backend/tests/ -v` — fully green (a red test is a regression).
2. `verify`-style manual pass: run the app, exercise the panel (ok / degraded / unavailable states), confirm no browser request ever carries the bearer key (devtools network tab).
3. One real v2 backtest context check with the key set: `load_news_sentiment(list(DJIA_30), <recent trading timestamp>)` returns populated entries with `rationale`.
4. `/code-review` on each PR before merge (loop protocol).
