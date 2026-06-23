"""Contract + integration tests for the Agent-Environment Protocol (v1).

Uses synthetic in-memory market data so no Alpaca/Yahoo network access is
required. The whole protocol stack is exercised through the public HTTP API.
"""

import sys
import time
import uuid
from pathlib import Path

import pandas as pd
import pytest
import pytz
from fastapi.testclient import TestClient

from dashboard.backend.app import app  # noqa: E402

ET = pytz.timezone("US/Eastern")


def _synthetic_bars():
    times = []
    for day in ("2026-04-15", "2026-04-16"):
        for hour in (10, 11, 12, 13, 14, 15):
            times.append(ET.localize(pd.Timestamp(f"{day} {hour}:00")))
    idx = pd.DatetimeIndex(times)
    n = len(idx)
    data = {}
    for base, sym in ((100.0, "AAPL"), (200.0, "MSFT")):
        closes = [base + i * 0.5 for i in range(n)]
        data[sym] = pd.DataFrame(
            {
                "open": closes,
                "high": [c + 1 for c in closes],
                "low": [c - 1 for c in closes],
                "close": closes,
                "volume": [1_000_000] * n,
            },
            index=idx,
        )
    return data


class _FakeLoader:
    def fetch_bars(self, symbols, start, end):
        return _synthetic_bars()


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "protocol_test.db"

    import dashboard.backend.database as db_module
    import dashboard.backend.agent_store as agent_store_module
    import dashboard.backend.agent_version_store as version_module
    import dashboard.backend.run_store as run_store_module
    import dashboard.backend.external_backtest_service as ebs
    import dashboard.backend.run_service as run_service
    import dashboard.backend.api.agents as agents_api
    import dashboard.backend.api.agent_versions as versions_api
    import dashboard.backend.api.runs as runs_api
    import dashboard.backend.api.protocol_auth as protocol_auth

    test_db = db_module.BacktestDatabase(db_path=db_path)
    test_agents = agent_store_module.AgentStore(db_path=db_path)
    test_versions = version_module.AgentVersionStore(db_path=db_path)
    test_runs = run_store_module.RunStore(db_path=db_path)

    # Database
    monkeypatch.setattr(db_module, "db", test_db)
    monkeypatch.setattr(ebs, "db", test_db)
    monkeypatch.setattr(run_service, "db", test_db)
    monkeypatch.setattr(agents_api.agent_service, "db", test_db)

    # Agent store
    monkeypatch.setattr(agent_store_module, "agent_store", test_agents)
    monkeypatch.setattr(ebs, "agent_store", test_agents)
    monkeypatch.setattr(agents_api.agent_service, "agents", test_agents)
    monkeypatch.setattr(protocol_auth, "agent_store", test_agents)

    # Version store
    monkeypatch.setattr(version_module, "agent_version_store", test_versions)
    monkeypatch.setattr(versions_api.agent_service, "versions", test_versions)
    monkeypatch.setattr(runs_api, "agent_version_store", test_versions)

    # Run store
    monkeypatch.setattr(run_store_module, "run_store", test_runs)
    monkeypatch.setattr(run_service, "run_store", test_runs)
    monkeypatch.setattr(runs_api, "run_store", test_runs)

    # Synthetic data + fast, network-free finalize
    monkeypatch.setattr(ebs, "AlpacaDataLoader", _FakeLoader)
    monkeypatch.setattr(ebs.HourlyBacktester, "run_buyhold_baseline", lambda self: (None, None))
    monkeypatch.setattr(ebs.HourlyBacktester, "run_djia_baseline", lambda self: (None, None))
    monkeypatch.setattr(ebs, "DECISION_TIMEOUT_SECONDS", 300)

    # Isolate the in-memory run/session registries between tests.
    monkeypatch.setattr(run_service, "_runs", {})
    monkeypatch.setattr(ebs, "_sessions", {})

    return TestClient(app)


def _new_agent(client):
    headers = {"X-Session-Id": str(uuid.uuid4())}
    resp = client.post("/api/v1/agents", json={"name": "proto-agent"}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    return body["agent"]["agent_id"], body["api_key"], headers


def _new_version(client, agent_id, key):
    resp = client.post(
        f"/api/v1/agents/{agent_id}/versions",
        json={"version": "0.1.0", "model_backbones": ["claude-sonnet"]},
        headers={"X-API-Key": key},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["agent_version"]["agent_version_id"]


def _create_run(client, key, version_id, start="2026-04-15", end="2026-04-16"):
    resp = client.post(
        "/api/v1/runs",
        json={
            "agent_version_id": version_id,
            "environment": {"type": "backtest", "environment_id": "us-equity-hourly-v1"},
            "config": {"start_date": start, "end_date": end, "symbols": ["AAPL", "MSFT"]},
        },
        headers={"X-API-Key": key},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["run_id"]


def _wait_for_step(client, run_id, key, attempts=50):
    """Poll steps/next until an awaiting step or completion."""
    for _ in range(attempts):
        resp = client.get(f"/api/v1/runs/{run_id}/steps/next", headers={"X-API-Key": key})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        if body.get("status") != "loading":
            return body
        time.sleep(0.05)
    raise AssertionError("Run stayed in loading state")


# ----------------------------------------------------------------------
# Environment discovery
# ----------------------------------------------------------------------


def test_environment_discovery(client):
    listed = client.get("/api/v1/environments")
    assert listed.status_code == 200
    envs = listed.json()["environments"]
    assert any(e["environment_id"] == "us-equity-hourly-v1" for e in envs)

    one = client.get("/api/v1/environments/us-equity-hourly-v1")
    assert one.status_code == 200
    assert one.json()["type"] == "backtest"
    assert one.json()["supports_shorting"] is False

    missing = client.get("/api/v1/environments/does-not-exist")
    assert missing.status_code == 404


# ----------------------------------------------------------------------
# AgentVersion
# ----------------------------------------------------------------------


def test_create_and_get_agent_version(client):
    agent_id, key, _ = _new_agent(client)
    version_id = _new_version(client, agent_id, key)
    assert version_id.startswith("agv_")

    listed = client.get(f"/api/v1/agents/{agent_id}/versions", headers={"X-API-Key": key})
    assert listed.status_code == 200
    assert len(listed.json()["versions"]) == 1

    fetched = client.get(f"/api/v1/agent-versions/{version_id}", headers={"X-API-Key": key})
    assert fetched.status_code == 200
    av = fetched.json()["agent_version"]
    assert av["agent_id"] == agent_id
    assert av["model_backbones"] == ["claude-sonnet"]


def test_agent_version_requires_auth(client):
    agent_id, key, _ = _new_agent(client)
    resp = client.post(f"/api/v1/agents/{agent_id}/versions", json={"version": "0.1.0"})
    assert resp.status_code == 401


# ----------------------------------------------------------------------
# Run lifecycle
# ----------------------------------------------------------------------


def test_create_run_and_first_step(client):
    agent_id, key, _ = _new_agent(client)
    version_id = _new_version(client, agent_id, key)
    run_id = _create_run(client, key, version_id)
    assert run_id.startswith("run_")

    step = _wait_for_step(client, run_id, key)
    assert step["status"] == "awaiting_decision"
    assert step["step_id"].startswith("step_")
    assert step["sequence"] == 0
    assert "observation" in step
    assert "portfolio" in step["observation"]
    assert step["constraints"]["allow_short"] is False


def test_create_run_requires_api_key(client):
    resp = client.post("/api/v1/runs", json={"config": {"start_date": "2026-04-15", "end_date": "2026-04-16"}})
    assert resp.status_code == 401


def test_submit_hold(client):
    agent_id, key, _ = _new_agent(client)
    version_id = _new_version(client, agent_id, key)
    run_id = _create_run(client, key, version_id)
    step = _wait_for_step(client, run_id, key)

    resp = client.post(
        f"/api/v1/runs/{run_id}/steps/{step['step_id']}/decision",
        json={"idempotency_key": str(uuid.uuid4()), "orders": []},
        headers={"X-API-Key": key},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["accepted"] is True
    assert body["validation"]["passed"] is True
    assert body["fills"] == []


def test_submit_valid_order(client):
    agent_id, key, _ = _new_agent(client)
    version_id = _new_version(client, agent_id, key)
    run_id = _create_run(client, key, version_id)
    step = _wait_for_step(client, run_id, key)

    resp = client.post(
        f"/api/v1/runs/{run_id}/steps/{step['step_id']}/decision",
        json={
            "idempotency_key": str(uuid.uuid4()),
            "orders": [{"symbol": "AAPL", "side": "buy", "quantity_type": "shares", "quantity": 10, "order_type": "market"}],
            "confidence": 0.8,
            "rationale": "momentum positive",
        },
        headers={"X-API-Key": key},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["accepted"] is True
    assert len(body["fills"]) == 1
    assert body["fills"][0]["symbol"] == "AAPL"
    assert body["fills"][0]["filled_quantity"] == 10
    assert body["portfolio_after"]["cash"] < 100000


def test_reject_invalid_symbol(client):
    agent_id, key, _ = _new_agent(client)
    version_id = _new_version(client, agent_id, key)
    run_id = _create_run(client, key, version_id)
    step = _wait_for_step(client, run_id, key)

    resp = client.post(
        f"/api/v1/runs/{run_id}/steps/{step['step_id']}/decision",
        json={
            "idempotency_key": str(uuid.uuid4()),
            "orders": [{"symbol": "NOTREAL", "side": "buy", "quantity": 5}],
        },
        headers={"X-API-Key": key},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    rejections = body["validation"]["rejections"]
    assert any(r["reason"] == "invalid_symbol" for r in rejections)
    assert body["fills"] == []


def test_reject_insufficient_cash(client):
    agent_id, key, _ = _new_agent(client)
    version_id = _new_version(client, agent_id, key)
    run_id = _create_run(client, key, version_id)
    step = _wait_for_step(client, run_id, key)

    resp = client.post(
        f"/api/v1/runs/{run_id}/steps/{step['step_id']}/decision",
        json={
            "idempotency_key": str(uuid.uuid4()),
            "orders": [{"symbol": "AAPL", "side": "buy", "quantity": 10000}],
        },
        headers={"X-API-Key": key},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    rejections = body["validation"]["rejections"]
    assert any(r["reason"] == "insufficient_cash" for r in rejections)
    assert body["fills"] == []


def test_idempotent_duplicate_submission(client):
    agent_id, key, _ = _new_agent(client)
    version_id = _new_version(client, agent_id, key)
    run_id = _create_run(client, key, version_id)
    step = _wait_for_step(client, run_id, key)

    idem = str(uuid.uuid4())
    payload = {
        "idempotency_key": idem,
        "orders": [{"symbol": "AAPL", "side": "buy", "quantity": 5}],
    }
    first = client.post(
        f"/api/v1/runs/{run_id}/steps/{step['step_id']}/decision",
        json=payload,
        headers={"X-API-Key": key},
    )
    second = client.post(
        f"/api/v1/runs/{run_id}/steps/{step['step_id']}/decision",
        json=payload,
        headers={"X-API-Key": key},
    )
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["decision_id"] == second.json()["decision_id"]


def test_conflicting_decision_on_finalized_step(client):
    agent_id, key, _ = _new_agent(client)
    version_id = _new_version(client, agent_id, key)
    run_id = _create_run(client, key, version_id)
    step = _wait_for_step(client, run_id, key)
    step_id = step["step_id"]

    first = client.post(
        f"/api/v1/runs/{run_id}/steps/{step_id}/decision",
        json={"idempotency_key": str(uuid.uuid4()), "orders": []},
        headers={"X-API-Key": key},
    )
    assert first.status_code == 200

    conflict = client.post(
        f"/api/v1/runs/{run_id}/steps/{step_id}/decision",
        json={"idempotency_key": str(uuid.uuid4()), "orders": [{"symbol": "AAPL", "side": "buy", "quantity": 1}]},
        headers={"X-API-Key": key},
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["error"]["code"] == "step_already_finalized"


def test_timeout_generates_hold(client, monkeypatch):
    import dashboard.backend.external_backtest_service as ebs

    agent_id, key, _ = _new_agent(client)
    version_id = _new_version(client, agent_id, key)

    monkeypatch.setattr(ebs, "DECISION_TIMEOUT_SECONDS", 0.01)
    run_id = _create_run(client, key, version_id)

    # Poll to completion: every step auto-holds because the deadline elapses.
    for _ in range(200):
        body = _wait_for_step(client, run_id, key)
        if body.get("status") == "completed":
            break
        time.sleep(0.02)
    else:
        raise AssertionError("Run did not complete via timeouts")

    steps = client.get(f"/api/v1/runs/{run_id}/steps", headers={"X-API-Key": key}).json()["steps"]
    assert steps
    assert all(s["status"] == "timed_out" for s in steps)


def test_full_run_to_completion_and_result(client):
    agent_id, key, _ = _new_agent(client)
    version_id = _new_version(client, agent_id, key)
    run_id = _create_run(client, key, version_id)

    for _ in range(200):
        body = _wait_for_step(client, run_id, key)
        if body.get("status") == "completed":
            break
        step_id = body["step_id"]
        resp = client.post(
            f"/api/v1/runs/{run_id}/steps/{step_id}/decision",
            json={"idempotency_key": str(uuid.uuid4()), "orders": []},
            headers={"X-API-Key": key},
        )
        assert resp.status_code == 200, resp.text
    else:
        raise AssertionError("Run did not complete")

    status = client.get(f"/api/v1/runs/{run_id}/status", headers={"X-API-Key": key}).json()
    assert status["status"] == "completed"

    result = client.get(f"/api/v1/runs/{run_id}/result", headers={"X-API-Key": key})
    assert result.status_code == 200, result.text
    rbody = result.json()
    assert "metrics" in rbody
    assert "equity_curve" in rbody

    metrics = client.get(f"/api/v1/runs/{run_id}/metrics", headers={"X-API-Key": key}).json()
    assert "total_return" in metrics["metrics"]


def test_run_result_before_completion(client):
    agent_id, key, _ = _new_agent(client)
    version_id = _new_version(client, agent_id, key)
    run_id = _create_run(client, key, version_id)
    _wait_for_step(client, run_id, key)

    resp = client.get(f"/api/v1/runs/{run_id}/result", headers={"X-API-Key": key})
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"]["code"] == "run_not_completed"


def test_run_access_control(client):
    agent_id, key, _ = _new_agent(client)
    version_id = _new_version(client, agent_id, key)
    run_id = _create_run(client, key, version_id)

    other_id, other_key, _ = _new_agent(client)
    resp = client.get(f"/api/v1/runs/{run_id}", headers={"X-API-Key": other_key})
    assert resp.status_code == 403
