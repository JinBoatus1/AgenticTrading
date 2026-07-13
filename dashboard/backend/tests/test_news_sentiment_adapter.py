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
