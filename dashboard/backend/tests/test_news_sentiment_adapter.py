from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from dashboard.backend.integrations import news_sentiment as ns
from dashboard.backend.tests.test_news_sentiment_fixture import (
    load_signals_fixture,
    load_signals_wire_fixture,
)


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


# --- Live wire-shape coverage (staleness_hours / degraded / 304) --------------
# The vendored on-disk fixture omits `staleness_hours` and is `status: ok`, so
# these branches are only reachable through the stripped-and-injected wire shape
# (contract §"Producer response shape"). See signals-wire-fixture.json.


def test_wire_shape_passes_staleness_hours_through(monkeypatch):
    """The panel surfaces the server-injected `staleness_hours` verbatim — the
    documented origin of the "Updated Xh ago" header. Unreachable via the
    on-disk fixture, which has no such key."""
    body = load_signals_wire_fixture()
    monkeypatch.setattr(ns, "_http_get", lambda **kw: _fake_response(body=body))
    payload = ns.get_latest_panel_payload(["MSFT", "NVDA"])
    assert payload["staleness_hours"] == body["staleness_hours"]
    assert payload["staleness_hours"] is not None  # the whole point vs on-disk fixture


def test_degraded_artifact_is_usable_projected_and_logged(monkeypatch, caplog):
    """A `degraded` artifact is still usable (contract §"Error & degraded
    handling"): the panel projects its signals and passes status/status_reason
    through, and the adapter logs the reason so the run stays auditable."""
    body = dict(load_signals_wire_fixture())
    body["status"] = "degraded"
    body["status_reason"] = "1 of 3 sources timed out"
    monkeypatch.setattr(ns, "_http_get", lambda **kw: _fake_response(body=body))
    with caplog.at_level("WARNING"):
        payload = ns.get_latest_panel_payload(["MSFT", "NVDA"])
    assert payload["signals"]                       # degraded != empty — still projected
    assert payload["status"] == "degraded"
    assert payload["status_reason"] == "1 of 3 sources timed out"
    assert any("degraded" in r.getMessage() for r in caplog.records)


def test_degraded_artifact_still_projects_in_backtest_path(monkeypatch):
    """`get_news_sentiment` (the per-step backtest loader) does not branch on
    status: a degraded-but-usable artifact still projects its signals rather
    than collapsing to empty."""
    body = dict(load_signals_wire_fixture())
    body["status"] = "degraded"
    body["status_reason"] = "partial feed"
    monkeypatch.setattr(ns, "_http_get", lambda **kw: _fake_response(body=body))
    ts = datetime(2026, 7, 10, 15, 0, tzinfo=timezone.utc)
    out = ns.get_news_sentiment(["MSFT", "NVDA"], ts)
    assert out["news_sentiment"]                    # non-empty: degraded is still projected
    assert out["news_overview"] == body["news_overview"]


def test_304_revalidation_serves_cached_body(monkeypatch):
    """A conditional GET that returns 304 serves the previously cached body
    (the latest-read path always sends If-None-Match). The on-disk fixture
    tests never reach this branch."""
    body = load_signals_wire_fixture()
    responses = [
        _fake_response(body=body, etag='"w1"'),
        _fake_response(status=304, body={}, etag='"w1"'),
    ]
    monkeypatch.setattr(ns, "_http_get", lambda **kw: responses.pop(0))
    first = ns.get_latest_panel_payload(["MSFT"])
    assert first["staleness_hours"] == body["staleness_hours"]
    second = ns.get_latest_panel_payload(["MSFT"])   # 304 -> cached body reused, not refetched
    assert second["staleness_hours"] == body["staleness_hours"]
    assert not responses                             # both queued responses consumed
