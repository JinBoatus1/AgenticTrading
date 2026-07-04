"""Adversarial-review fixes for the /api/v2 merge (reconciliation hardening).

Each test pins a finding confirmed by the 5-lens review of merge a93d39d:
v2 code written against the pre-hardening flat backend inherited failure
modes this PR had already fixed on the v1 surface.
"""

import time
import uuid

import pytest
from fastapi.testclient import TestClient

import dashboard.backend.api.v2.runs as runs_mod
import dashboard.backend.execution.backtest_backend as bb_mod
from dashboard.backend.api.v2.errors import ApiError
from dashboard.backend.api.v2.rate_limit import TokenBucketLimiter
from dashboard.backend.app import app
from dashboard.backend.execution.backtest_backend import BacktestBackend
from dashboard.backend.tests._v2_fakes import FakeBackend

client = TestClient(app)


def _agent(name):
    r = client.post("/api/v2/agents", json={"name": name}).json()
    return r["api_key"], r["session_id"], r["agent_id"]


# -- SystemExit guard on the background loader ------------------------------

def test_background_load_systemexit_marks_run_failed(monkeypatch):
    """AlpacaDataLoader sys.exit()s when creds are absent; a daemon thread
    silently swallows an uncaught SystemExit, so `except Exception` alone
    leaves the run stuck in "loading" forever (the B0 failure mode, fixed on
    v1 in this PR but not ported to the v2 backend by the merge)."""

    class _Boom:
        def __init__(self):
            raise SystemExit(1)

    monkeypatch.setattr(bb_mod.ext, "AlpacaDataLoader", _Boom)
    backend = BacktestBackend(
        run_id="run_se_guard", session_id="sess_se", agent_name="a",
        model_name="m", start_date="2026-04-15", end_date="2026-04-16",
    )
    backend.start_background_load()
    deadline = time.time() + 5
    while time.time() < deadline and backend.session.status == "loading":
        time.sleep(0.02)
    assert backend.session.status == "failed"
    assert backend.session.error


# -- apply_decisions maps engine rejections to typed errors ------------------

class _RejectingSession:
    step_index = 3
    status = "waiting_decision"

    def __init__(self, result):
        self._result = result

    def submit_decisions(self, payload):
        return self._result


def _backend_with(session):
    backend = BacktestBackend.__new__(BacktestBackend)
    backend.run_id = "run_reject"
    backend.session = session
    return backend


def test_apply_decisions_late_decision_raises_step_already_closed():
    """A deadline-expired submission must surface as the spec'd
    step_already_closed error, not as an accepted-looking ack attributed to
    decision_source="external_agent"."""
    backend = _backend_with(_RejectingSession({
        "accepted": False, "error": "step_already_closed",
        "outcome": "timeout_hold", "next_step": 4, "status": "waiting_decision",
    }))
    with pytest.raises(ApiError) as ei:
        backend.apply_decisions([])
    assert ei.value.code == "step_already_closed"
    assert ei.value.status == 409
    assert ei.value.retryable is True
    assert ei.value.details["outcome"] == "timeout_hold"


def test_apply_decisions_completed_run_raises_invalid_status():
    backend = _backend_with(_RejectingSession({
        "accepted": False, "error": "backtest_already_completed", "run_id": "r",
    }))
    with pytest.raises(ApiError) as ei:
        backend.apply_decisions([])
    assert ei.value.code == "invalid_status"
    assert ei.value.status == 409


def test_apply_decisions_not_waiting_raises_invalid_status_with_state():
    backend = _backend_with(_RejectingSession({
        "accepted": False, "error": "invalid_status:loading",
    }))
    with pytest.raises(ApiError) as ei:
        backend.apply_decisions([])
    assert ei.value.code == "invalid_status"
    assert "loading" in ei.value.message


# -- v2 run lookup: no existence oracle --------------------------------------

def test_v2_run_lookup_is_not_an_existence_oracle():
    """404 bodies for "doesn't exist" and "not yours" must be identical in
    shape — a message-text difference lets any registered key enumerate
    which run ids exist."""
    _, sid_a, _ = _agent("oracle-owner")
    key_b, _, _ = _agent("oracle-prober")
    run_id = f"run_oracle_{uuid.uuid4().hex[:6]}"
    runs_mod.register_run(run_id, FakeBackend(run_id=run_id, session_id=sid_a), sid_a)

    denied = client.get(f"/api/v2/runs/{run_id}", headers={"X-API-Key": key_b})
    missing = client.get(
        f"/api/v2/runs/run_missing_{uuid.uuid4().hex[:6]}", headers={"X-API-Key": key_b}
    )
    assert denied.status_code == 404 and missing.status_code == 404
    d, m = denied.json()["error"], missing.json()["error"]
    assert d["code"] == m["code"] == "run_not_found"
    # Same template both ways: only the caller's own probed id may differ.
    assert d["message"] == f"Run {run_id} not found"
    assert m["message"].endswith("not found")


# -- per-agent active-run cap -------------------------------------------------

class _StubBackend:
    loop = "lockstep"
    news_sentiment_source = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def start_background_load(self):
        pass

    def status(self):
        return {"status": "waiting_decision"}


def test_create_run_enforces_per_agent_active_cap(monkeypatch):
    """v1 got MAX_ACTIVE_RUNS_PER_AGENT in H4; the same agent identity must
    not be able to sidestep it by creating runs through v2 instead."""
    key, _, _ = _agent("capped-agent")
    monkeypatch.setattr(runs_mod, "BacktestBackend", _StubBackend)
    monkeypatch.setattr(runs_mod, "MAX_ACTIVE_RUNS_PER_AGENT", 2)

    body = {"start_date": "2026-04-15", "end_date": "2026-04-16"}
    headers = {"X-API-Key": key}
    assert client.post("/api/v2/runs", json=body, headers=headers).status_code == 200
    assert client.post("/api/v2/runs", json=body, headers=headers).status_code == 200
    r3 = client.post("/api/v2/runs", json=body, headers=headers)
    assert r3.status_code == 429
    err = r3.json()["error"]
    assert err["code"] == "too_many_active_runs"
    assert err["details"]["limit"] == 2


def test_cap_ignores_other_agents_and_terminal_runs(monkeypatch):
    key, _, _ = _agent("capped-agent-2")

    class _DoneBackend(_StubBackend):
        def status(self):
            return {"status": "completed"}

    monkeypatch.setattr(runs_mod, "MAX_ACTIVE_RUNS_PER_AGENT", 1)
    monkeypatch.setattr(runs_mod, "BacktestBackend", _DoneBackend)
    body = {"start_date": "2026-04-15", "end_date": "2026-04-16"}
    headers = {"X-API-Key": key}
    # A terminal run does not count against the cap.
    assert client.post("/api/v2/runs", json=body, headers=headers).status_code == 200
    assert client.post("/api/v2/runs", json=body, headers=headers).status_code == 200


# -- registration flood control ----------------------------------------------

def test_v2_registration_is_rate_limited(monkeypatch):
    """POST /api/v2/agents is unauthenticated by design; without a per-client
    budget it is an unbounded DB-write + rate-limit-bucket flood vector."""
    import dashboard.backend.api.v2.agents as agents_mod
    from dashboard.backend.api.rate_limit import FixedWindowRateLimiter

    monkeypatch.setattr(
        agents_mod, "_register_rate_limiter",
        FixedWindowRateLimiter(max_events=3, window_seconds=3600),
    )
    headers = {"X-Browser-Id": "reg-flood-client"}
    codes = [
        client.post("/api/v2/agents", json={"name": f"flood-{i}"}, headers=headers).status_code
        for i in range(5)
    ]
    assert codes[:3] == [200, 200, 200]
    assert set(codes[3:]) == {429}


# -- token-bucket registry is bounded ------------------------------------------

def test_token_bucket_registry_is_bounded():
    lim = TokenBucketLimiter(per_minute=60, max_buckets=100)
    for i in range(600):
        lim.check(f"agent_{i}")
    assert len(lim._buckets) <= 100


# -- CORS exposes the v2 rate-limit headers ------------------------------------

def test_rate_limit_headers_exposed_to_cors_clients():
    """The spec promises X-RateLimit-*/Retry-After to clients; without
    Access-Control-Expose-Headers browsers strip them from fetch() results."""
    key, _, _ = _agent("cors-agent")
    r = client.get(
        "/api/v2/agents/me",
        headers={"X-API-Key": key, "Origin": "https://agentic-trading-lab.vercel.app"},
    )
    exposed = r.headers.get("access-control-expose-headers", "").lower()
    for header in ("x-ratelimit-limit", "x-ratelimit-remaining",
                   "x-ratelimit-reset", "retry-after"):
        assert header in exposed, f"{header} missing from {exposed!r}"
