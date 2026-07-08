"""MEDIUM #2 / #3 — /backtest routes hardening.

#3: GET /runs/{run_id}/plot.png must not block the event loop (sync handler ->
    threadpool), must not re-import/re-configure matplotlib per request, and
    should cache the immutable rendered PNG per run_id.
#2: POST /backtest/run must not let an anonymous caller burn operator LLM
    credits — model allowlist, prompt size cap, date-range cap, write rate limit.
"""

import inspect
import uuid

import pytest
from fastapi.testclient import TestClient

from dashboard.backend.app import app
from dashboard.backend.api.rate_limit import FixedWindowRateLimiter
import dashboard.backend.api.routers.backtests as bt


# ===========================================================================
# #3 — plot.png: event loop + caching
# ===========================================================================

def test_plot_png_handler_is_sync_offloaded():
    # Sync def -> FastAPI runs the CPU-bound render in a threadpool, not on the
    # event loop. (Was `async def`, which blocked the loop for the whole render.)
    assert not inspect.iscoroutinefunction(bt.get_run_plot)


def test_plot_png_matplotlib_hoisted_to_module():
    # The renderer no longer imports/configures matplotlib per call.
    src = inspect.getsource(bt._render_run_plot_png)
    assert "import matplotlib" not in src
    assert 'matplotlib.use(' not in src
    # It's configured once at module import instead.
    assert bt.matplotlib.get_backend().lower() == "agg"


def test_plot_png_cached_per_run(monkeypatch):
    bt._render_run_plot_png.cache_clear()
    calls = {"get_run": 0, "equity": 0}
    fake_run = {
        "session_id": None, "created_at": "2026-05-01T10:00:00", "agent_name": "Agent",
        "start_date": "2026-05-01", "end_date": "2026-05-07", "mode": "safe_trading",
        "baseline_buyhold_run_id": None, "baseline_djia_run_id": None,
    }

    def fake_get_run(rid):
        calls["get_run"] += 1
        return fake_run

    def fake_equity(rid):
        calls["equity"] += 1
        return [{"timestamp": "2026-05-01T10:00:00", "equity": 100000},
                {"timestamp": "2026-05-01T11:00:00", "equity": 101000}]

    monkeypatch.setattr(bt.db, "get_run", fake_get_run)
    monkeypatch.setattr(bt.db, "get_equity_curve", fake_equity)
    monkeypatch.setattr(bt, "filter_market_hours", lambda pts: pts)  # isolate caching

    first = bt._render_run_plot_png("run_x")
    second = bt._render_run_plot_png("run_x")

    assert first == second
    assert first[:8] == b"\x89PNG\r\n\x1a\n"      # valid PNG
    assert calls["get_run"] == 1                  # 2nd call served from cache
    bt._render_run_plot_png.cache_clear()


def test_plot_png_missing_run_not_cached(monkeypatch):
    # A 404 must not be cached: a run that appears later should still render.
    bt._render_run_plot_png.cache_clear()
    from fastapi import HTTPException
    monkeypatch.setattr(bt.db, "get_run", lambda rid: None)
    with pytest.raises(HTTPException):
        bt._render_run_plot_png("missing")
    # Nothing cached -> a second call re-queries (would render if data existed).
    hits = {"n": 0}

    def counting_get_run(rid):
        hits["n"] += 1
        return None

    monkeypatch.setattr(bt.db, "get_run", counting_get_run)
    with pytest.raises(HTTPException):
        bt._render_run_plot_png("missing")
    assert hits["n"] == 1  # re-evaluated, not served from a cached exception
    bt._render_run_plot_png.cache_clear()


# ===========================================================================
# #2 — /backtest/run: cost-abuse hardening
# ===========================================================================

class _Spy:
    def __init__(self):
        self.calls = 0
        self.last_args = None

    def __call__(self, *a, **k):
        self.calls += 1
        self.last_args = a


@pytest.fixture(autouse=True)
def _reset_backtest_guards(monkeypatch):
    bt._backtest_rate_limiter.reset()
    bt.backtest_status.update({"running": False, "error": None, "runs_count": 0})
    # Safety net: no test in this file may launch a real backtest thread.
    monkeypatch.setattr(bt, "run_backtest_background", lambda *a, **k: None)
    yield
    bt._backtest_rate_limiter.reset()


def _sess():
    return {"X-Session-Id": str(uuid.uuid4())}


def test_backtest_run_valid_request_ok():
    resp = TestClient(app).post(
        "/backtest/run",
        json={"start_date": "2026-05-01", "end_date": "2026-05-07"},
        headers=_sess(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert "session_id" in body


def test_backtest_run_targets_builtin_agent_session(client, monkeypatch):
    """Discord (and website) can pass agent_id so runs land on the agent card."""
    spy = _Spy()
    monkeypatch.setattr(bt, "run_backtest_background", spy)

    owner = str(uuid.uuid4())
    created = client.post(
        "/api/v1/agents",
        json={"name": "Discord Card Bot", "agent_type": "builtin"},
        headers={"X-Session-Id": owner},
    ).json()
    agent_session = created["session_id"]
    agent_id = created["agent"]["agent_id"]

    resp = client.post(
        "/backtest/run",
        json={
            "start_date": "2026-05-01",
            "end_date": "2026-05-02",
            "strategy_prompt": "buy low sell high",
            "agent_id": agent_id,
        },
        headers={"X-Session-Id": str(uuid.uuid4())},
    )
    assert resp.status_code == 200
    assert resp.json()["session_id"] == agent_session
    assert spy.calls == 1
    assert spy.last_args[2] == agent_session


def test_backtest_run_rejects_external_agent_id(client):
    owner = str(uuid.uuid4())
    created = client.post(
        "/api/v1/agents",
        json={"name": "External Only", "agent_type": "external"},
        headers={"X-Session-Id": owner},
    ).json()
    agent_id = created["agent"]["agent_id"]

    resp = client.post(
        "/backtest/run",
        json={"start_date": "2026-05-01", "end_date": "2026-05-02", "agent_id": agent_id},
        headers=_sess(),
    )
    assert resp.status_code == 422


@pytest.fixture
def client():
    return TestClient(app)


@pytest.mark.parametrize("model", [
    # Exactly the options the dashboard UI dropdown (app.html) offers. A pricing-
    # table allowlist previously 422'd gpt-5.2 / gpt-5-mini / deepseek-* / gemini-*,
    # breaking the UI's own model choices.
    "claude-haiku-4.5", "claude-sonnet-4.6", "claude-opus-4.7",
    "gpt-5.2", "gpt-5-mini", "deepseek-v4-flash", "deepseek-v4-pro",
    "gemini-3.5-flash", "gemini-2.5-pro",
    "openai/gpt-5.5", "google/gemini-3.1-pro-preview",
])
def test_backtest_run_accepts_frontend_model_options(model):
    resp = TestClient(app).post(
        "/backtest/run",
        json={"start_date": "2026-05-01", "end_date": "2026-05-02", "model": model},
        headers=_sess(),
    )
    assert resp.status_code == 200, (model, resp.text)


@pytest.mark.parametrize("model", [
    "bad model with spaces", "x; rm -rf /", "a" * 100, "m\nnewline", "café",
])
def test_backtest_run_rejects_malformed_model(monkeypatch, model):
    spy = _Spy()
    monkeypatch.setattr(bt, "run_backtest_background", spy)
    resp = TestClient(app).post(
        "/backtest/run",
        json={"start_date": "2026-05-01", "end_date": "2026-05-02", "model": model},
        headers=_sess(),
    )
    assert resp.status_code == 422, (model, resp.text)
    assert spy.calls == 0  # nothing scheduled


def test_backtest_run_rejects_oversized_prompt(monkeypatch):
    spy = _Spy()
    monkeypatch.setattr(bt, "run_backtest_background", spy)
    resp = TestClient(app).post(
        "/backtest/run",
        json={"start_date": "2026-05-01", "end_date": "2026-05-02",
              "strategy_prompt": "x" * 5000},
        headers=_sess(),
    )
    assert resp.status_code == 422
    assert spy.calls == 0


def test_backtest_run_rejects_excessive_date_range(monkeypatch):
    spy = _Spy()
    monkeypatch.setattr(bt, "run_backtest_background", spy)
    resp = TestClient(app).post(
        "/backtest/run",
        json={"start_date": "2020-01-01", "end_date": "2026-01-01"},
        headers=_sess(),
    )
    assert resp.status_code == 422
    assert spy.calls == 0


def test_backtest_run_rejects_bad_date_format():
    resp = TestClient(app).post(
        "/backtest/run",
        json={"start_date": "05/01/2026", "end_date": "2026-05-02"},
        headers=_sess(),
    )
    assert resp.status_code == 422


def test_backtest_run_rate_limited_per_client(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(
        bt, "_backtest_rate_limiter",
        FixedWindowRateLimiter(max_events=2, window_seconds=3600, clock=lambda: now[0]),
    )
    client = TestClient(app)
    headers = _sess()  # same session -> same rate key across the three calls
    body = {"start_date": "2026-05-01", "end_date": "2026-05-02"}
    assert client.post("/backtest/run", json=body, headers=headers).status_code == 200
    assert client.post("/backtest/run", json=body, headers=headers).status_code == 200
    assert client.post("/backtest/run", json=body, headers=headers).status_code == 429
