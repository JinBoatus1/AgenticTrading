"""HTTP-level tests for the v2 runs endpoints.

These drive the real FastAPI stack (auth dependency -> scope -> session
ownership -> error envelope -> rate limit) by registering an offline
FakeBackend under a run_id whose session_id matches a freshly-registered
agent. This avoids Alpaca/network while still exercising the wire contract.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

import api.v2.runs as runs_mod  # noqa: E402
import rate_limit  # noqa: E402
from agent_store import agent_store  # noqa: E402
from app import app  # noqa: E402
from tests._v2_fakes import FakeBackend  # noqa: E402

client = TestClient(app)


def _agent(name):
    """Register an agent; return (api_key, session_id, agent_id)."""
    r = client.post("/api/v2/agents", json={"name": name}).json()
    return r["api_key"], r["session_id"], r["agent_id"]


def _register_run(run_id, session_id, total_steps=2):
    backend = FakeBackend(run_id=run_id, total_steps=total_steps, session_id=session_id)
    runs_mod.register_run(run_id, backend, session_id)
    return backend


# -- security boundary: cross-agent access ---------------------------------

def test_cross_agent_cannot_read_run_returns_404_envelope():
    key_a, sid_a, _ = _agent("owner-a")
    key_b, _, _ = _agent("intruder-b")
    _register_run("run_iso_http", sid_a)
    r = client.get("/api/v2/runs/run_iso_http/context", headers={"X-API-Key": key_b})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "run_not_found"


# -- scope enforcement at the HTTP layer -----------------------------------

def test_missing_scope_returns_403_envelope():
    key, _, agent_id = _agent("scoped-agent")
    conn = agent_store._get_connection()
    conn.execute("UPDATE external_agents SET scopes=? WHERE agent_id=?",
                 ("runs:read", agent_id))
    conn.commit()
    # context requires context:read, which we just removed
    r = client.get("/api/v2/runs/any_run/context", headers={"X-API-Key": key})
    assert r.status_code == 403
    body = r.json()
    assert body["error"]["code"] == "forbidden_scope"
    assert body["error"]["details"]["required"] == "context:read"


# -- rate limiting at the HTTP layer ---------------------------------------

def test_rate_limit_returns_429_envelope_with_retry_after():
    key, sid, agent_id = _agent("rl-agent")
    _register_run("run_rl_http", sid)
    # Drain the bucket so the next call is denied.
    rate_limit.limiter._buckets[agent_id] = (0.0, time.monotonic())
    r = client.get("/api/v2/runs/run_rl_http/context", headers={"X-API-Key": key})
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "rate_limited"
    assert "Retry-After" in r.headers


# -- error envelope: result before completion ------------------------------

def test_result_before_completion_returns_409_envelope():
    key, sid, _ = _agent("res-agent")
    _register_run("run_res_http", sid)
    r = client.get("/api/v2/runs/run_res_http/result", headers={"X-API-Key": key})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "invalid_status"


# -- M2: request-body validation flows through the uniform envelope --------

def test_invalid_create_body_returns_validation_failed_envelope():
    key, _, _ = _agent("val-agent")
    r = client.post("/api/v2/runs", headers={"X-API-Key": key},
                    json={"mode": "live", "start_date": "2026-01-01",
                          "end_date": "2026-01-02"})
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["code"] == "validation_failed"
    assert "details" in body["error"]


# -- M1: cancel transitions context to a 'closed' envelope -----------------

def test_cancel_then_context_reports_closed():
    key, sid, _ = _agent("cancel-agent")
    _register_run("run_cancel_http", sid)
    h = {"X-API-Key": key}
    c = client.post("/api/v2/runs/run_cancel_http/cancel", headers=h)
    assert c.status_code == 200
    assert c.json()["status"] == "closed"
    ctx = client.get("/api/v2/runs/run_cancel_http/context", headers=h)
    assert ctx.status_code == 200
    assert ctx.json()["status"] == "closed"


# -- N1: decisions log reads through the backend interface ------------------

def test_decisions_log_returns_recorded_decisions():
    key, sid, _ = _agent("log-agent")
    _register_run("run_log_http", sid)
    h = {"X-API-Key": key}
    sub = client.post("/api/v2/runs/run_log_http/decisions", headers=h, json={
        "idempotency_key": "k1",
        "actions": [{"action": "buy", "symbol": "AAPL", "confidence": 0.7,
                     "reasoning": "momentum looks strong", "position_size": 3}],
    })
    assert sub.status_code == 200
    r = client.get("/api/v2/runs/run_log_http/decisions", headers=h)
    assert r.status_code == 200
    decisions = r.json()["decisions"]
    assert isinstance(decisions, list)
    assert len(decisions) >= 1
