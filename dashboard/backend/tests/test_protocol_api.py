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
    import dashboard.backend.domain.agents.repository as agent_store_module
    import dashboard.backend.domain.agents.version_repository as version_module
    import dashboard.backend.domain.runs.repository as run_store_module
    import dashboard.backend.domain.backtesting.external_run_service as ebs
    import dashboard.backend.domain.runs.service as run_service
    import dashboard.backend.api.routers.agents as agents_api
    import dashboard.backend.api.routers.agent_versions as versions_api
    import dashboard.backend.api.routers.runs as runs_api
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


def test_reject_oversized_order_position_cap(client):
    """A single BUY that would exceed max_position_weight (0.25 of equity) is
    rejected on its own and produces no fill.

    With $100k equity the per-position cap ($25k) binds before cash ($100k), so
    an over-cap order is rejected as ``exceeds_max_position_weight`` (H2/H3
    constraint enforcement) rather than reaching the engine at all.
    """
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
    assert any(r["reason"] == "exceeds_max_position_weight" for r in rejections)
    assert body["fills"] == []


def test_reject_symbol_outside_allowed_list(client):
    """H2: symbols are validated against the run's constraint allow-list, not the
    whole DJIA-30 universe. JPM is a real DJIA-30 member but is not in this run's
    config.symbols (AAPL/MSFT), so it must be rejected as ``invalid_symbol``.
    """
    agent_id, key, _ = _new_agent(client)
    version_id = _new_version(client, agent_id, key)
    run_id = _create_run(client, key, version_id)
    step = _wait_for_step(client, run_id, key)

    resp = client.post(
        f"/api/v1/runs/{run_id}/steps/{step['step_id']}/decision",
        json={
            "idempotency_key": str(uuid.uuid4()),
            "orders": [{"symbol": "JPM", "side": "buy", "quantity": 5}],
        },
        headers={"X-API-Key": key},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    rejections = body["validation"]["rejections"]
    assert any(r["reason"] == "invalid_symbol" for r in rejections)
    assert body["fills"] == []


def test_reject_too_many_orders(client):
    """H2: a decision with more orders than max_orders (10) is rejected wholesale
    with 400 too_many_orders; the step stays open for a corrected resubmission.
    """
    agent_id, key, _ = _new_agent(client)
    version_id = _new_version(client, agent_id, key)
    run_id = _create_run(client, key, version_id)
    step = _wait_for_step(client, run_id, key)

    orders = [{"symbol": "AAPL", "side": "buy", "quantity": 1} for _ in range(11)]
    resp = client.post(
        f"/api/v1/runs/{run_id}/steps/{step['step_id']}/decision",
        json={"idempotency_key": str(uuid.uuid4()), "orders": orders},
        headers={"X-API-Key": key},
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"]["error"]["code"] == "too_many_orders"


def test_oversized_order_does_not_void_valid_orders(client):
    """H3: one over-cap order is rejected on its own; the other valid order in
    the same decision still executes (previously the batch could be voided).
    """
    agent_id, key, _ = _new_agent(client)
    version_id = _new_version(client, agent_id, key)
    run_id = _create_run(client, key, version_id)
    step = _wait_for_step(client, run_id, key)

    resp = client.post(
        f"/api/v1/runs/{run_id}/steps/{step['step_id']}/decision",
        json={
            "idempotency_key": str(uuid.uuid4()),
            "orders": [
                {"symbol": "AAPL", "side": "buy", "quantity": 400},  # ~$40k > $25k cap
                {"symbol": "MSFT", "side": "buy", "quantity": 5},    # ~$1k, well within cap
            ],
        },
        headers={"X-API-Key": key},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    filled_symbols = {f["symbol"] for f in body["fills"]}
    assert filled_symbols == {"MSFT"}, body
    assert any(
        r["reason"] == "exceeds_max_position_weight" and r["order"]["symbol"] == "AAPL"
        for r in body["validation"]["rejections"]
    )


def test_reject_nonfinite_quantity(client):
    """H3: a NaN/Infinity or absurd quantity is rejected at the schema boundary
    (422) instead of overflowing int() with a 500.
    """
    agent_id, key, _ = _new_agent(client)
    version_id = _new_version(client, agent_id, key)
    run_id = _create_run(client, key, version_id)
    step = _wait_for_step(client, run_id, key)

    # Over the finite upper bound (lt=1e12).
    over = client.post(
        f"/api/v1/runs/{run_id}/steps/{step['step_id']}/decision",
        json={
            "idempotency_key": str(uuid.uuid4()),
            "orders": [{"symbol": "AAPL", "side": "buy", "quantity": 1e13}],
        },
        headers={"X-API-Key": key},
    )
    assert over.status_code == 422, over.text

    # Infinity: previously reached int(inf) -> OverflowError -> 500. The client
    # JSON encoder refuses to emit `inf`, so post the raw `Infinity` token the
    # way a hand-rolled agent might; the server's json.loads accepts it and
    # Pydantic (allow_inf_nan=False) must reject it as 422, not 500.
    raw = (
        '{"idempotency_key": "%s", '
        '"orders": [{"symbol": "AAPL", "side": "buy", "quantity": Infinity}]}'
        % uuid.uuid4()
    )
    inf = client.post(
        f"/api/v1/runs/{run_id}/steps/{step['step_id']}/decision",
        content=raw,
        headers={"X-API-Key": key, "Content-Type": "application/json"},
    )
    assert inf.status_code == 422, inf.text


def test_reject_nondefault_initial_cash(client):
    """H2: create_run rejects a non-default config.initial_cash rather than
    silently ignoring it (the engine's starting capital is fixed).
    """
    agent_id, key, _ = _new_agent(client)
    version_id = _new_version(client, agent_id, key)

    resp = client.post(
        "/api/v1/runs",
        json={
            "agent_version_id": version_id,
            "environment": {"type": "backtest", "environment_id": "us-equity-hourly-v1"},
            "config": {
                "start_date": "2026-04-15",
                "end_date": "2026-04-16",
                "symbols": ["AAPL", "MSFT"],
                "initial_cash": 50000,
            },
        },
        headers={"X-API-Key": key},
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"]["error"]["code"] == "invalid_config"


def test_position_cap_accounts_for_intra_decision_accumulation(client):
    """H3 refinement: multiple BUYs of the same symbol in one decision are
    capped by their COMBINED resulting position, not each in isolation. Two
    AAPL buys of 200 (~$20k each) individually fit the $25k cap, but together
    ($40k) breach it, so the second must be rejected — otherwise order-splitting
    silently bypasses max_position_weight.
    """
    agent_id, key, _ = _new_agent(client)
    version_id = _new_version(client, agent_id, key)
    run_id = _create_run(client, key, version_id)
    step = _wait_for_step(client, run_id, key)

    resp = client.post(
        f"/api/v1/runs/{run_id}/steps/{step['step_id']}/decision",
        json={
            "idempotency_key": str(uuid.uuid4()),
            "orders": [
                {"symbol": "AAPL", "side": "buy", "quantity": 200},
                {"symbol": "AAPL", "side": "buy", "quantity": 200},
            ],
        },
        headers={"X-API-Key": key},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Only the first 200 shares fill; the accumulated 400 would breach the cap.
    total_filled = sum(f["filled_quantity"] for f in body["fills"] if f["symbol"] == "AAPL")
    assert total_filled == 200, body
    assert any(
        r["reason"] == "exceeds_max_position_weight" for r in body["validation"]["rejections"]
    ), body
    # Resulting AAPL position stays within the 25% cap ($25k of $100k equity).
    aapl = [p for p in body["portfolio_after"]["positions"] if p["symbol"] == "AAPL"]
    assert aapl and aapl[0]["market_value"] <= 25000, body


def test_engine_share_cap_does_not_void_valid_orders(client, monkeypatch):
    """H3 refinement: an order above the engine's hard 10k-share ceiling is
    rejected per-order (exceeds_max_order_size) instead of tripping the engine's
    all-or-nothing batch validator and voiding valid siblings.

    The per-position weight cap normally binds long before 10k shares, so lift
    it for this run to isolate the engine ceiling.
    """
    import dashboard.backend.domain.runs.environment as env_module

    monkeypatch.setitem(
        env_module.ENVIRONMENTS["us-equity-hourly-v1"]["constraints"],
        "max_position_weight",
        100.0,
    )

    agent_id, key, _ = _new_agent(client)
    version_id = _new_version(client, agent_id, key)
    run_id = _create_run(client, key, version_id)
    step = _wait_for_step(client, run_id, key)

    resp = client.post(
        f"/api/v1/runs/{run_id}/steps/{step['step_id']}/decision",
        json={
            "idempotency_key": str(uuid.uuid4()),
            "orders": [
                {"symbol": "AAPL", "side": "buy", "quantity": 11000},  # > 10k ceiling
                {"symbol": "MSFT", "side": "buy", "quantity": 5},       # valid sibling
            ],
        },
        headers={"X-API-Key": key},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert {f["symbol"] for f in body["fills"]} == {"MSFT"}, body
    assert any(
        r["reason"] == "exceeds_max_order_size" and r["order"]["symbol"] == "AAPL"
        for r in body["validation"]["rejections"]
    ), body


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
    import dashboard.backend.domain.backtesting.external_run_service as ebs

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
    # MEDIUM #9: ownership rejection uses the protocol error envelope, not a
    # bare-string detail.
    assert resp.json()["detail"]["error"]["code"] == "forbidden"


def test_run_not_found_error_envelope(client):
    """MEDIUM #9: a missing run returns the protocol error envelope with code
    run_not_found (was a bare-string detail that broke envelope parsing)."""
    _, key, _ = _new_agent(client)
    resp = client.get("/api/v1/runs/run_does_not_exist", headers={"X-API-Key": key})
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"]["code"] == "run_not_found"


def test_orphaned_run_denied_fail_closed(client):
    """A run with no owner agent_id must not be reachable by any authenticated
    agent. Regression for the IDOR fail-open: _require_run_owner previously
    allowed access whenever the run's agent_id was falsy; it must now fail
    closed. The API never creates such rows, so insert one straight into the
    RunStore the router uses."""
    import dashboard.backend.api.routers.runs as runs_api

    _, key, _ = _new_agent(client)
    orphan = runs_api.run_store.create_run(
        agent_id=None,
        agent_version_id=None,
        session_id=str(uuid.uuid4()),
        environment_id="us-equity-hourly-v1",
        environment_type="backtest",
        config={},
    )

    resp = client.get(
        f"/api/v1/runs/{orphan['run_id']}", headers={"X-API-Key": key}
    )
    assert resp.status_code == 403, resp.text


# ----------------------------------------------------------------------
# H4 — run lifecycle recovery, concurrency cap, idempotency scope, reaper
# ----------------------------------------------------------------------


def test_recover_orphaned_runs_fails_unfinished(client):
    """A run left 'running' by a crash/restart is marked failed on recovery — it
    can't resume (its in-memory engine session is gone) and must stop counting
    against the per-agent active cap."""
    import dashboard.backend.api.routers.runs as runs_api
    import dashboard.backend.domain.runs.service as run_service

    orphan = runs_api.run_store.create_run(
        agent_id="ag_orphan",
        agent_version_id=None,
        session_id=str(uuid.uuid4()),
        environment_id="us-equity-hourly-v1",
        environment_type="backtest",
        config={},
        status="running",
    )
    assert orphan["status"] == "running"

    recovered = run_service.recover_orphaned_runs()
    assert recovered >= 1
    assert runs_api.run_store.get_run(orphan["run_id"])["status"] == "failed"


def test_concurrent_run_cap(client, monkeypatch):
    """Once an agent has MAX_ACTIVE_RUNS_PER_AGENT non-terminal runs, another
    create is refused with 429 too_many_active_runs."""
    import dashboard.backend.domain.runs.service as run_service

    monkeypatch.setattr(run_service, "MAX_ACTIVE_RUNS_PER_AGENT", 2)

    agent_id, key, _ = _new_agent(client)
    version_id = _new_version(client, agent_id, key)
    _create_run(client, key, version_id)
    _create_run(client, key, version_id)

    third = client.post(
        "/api/v1/runs",
        json={
            "agent_version_id": version_id,
            "environment": {"type": "backtest", "environment_id": "us-equity-hourly-v1"},
            "config": {"start_date": "2026-04-15", "end_date": "2026-04-16", "symbols": ["AAPL", "MSFT"]},
        },
        headers={"X-API-Key": key},
    )
    assert third.status_code == 429, third.text
    assert third.json()["detail"]["error"]["code"] == "too_many_active_runs"


def test_idempotency_scoped_to_step(client):
    """The same idempotency_key reused on a DIFFERENT step must not replay the
    earlier step's result."""
    agent_id, key, _ = _new_agent(client)
    version_id = _new_version(client, agent_id, key)
    run_id = _create_run(client, key, version_id)

    step1 = _wait_for_step(client, run_id, key)
    reused = str(uuid.uuid4())
    r1 = client.post(
        f"/api/v1/runs/{run_id}/steps/{step1['step_id']}/decision",
        json={"idempotency_key": reused, "orders": []},
        headers={"X-API-Key": key},
    )
    assert r1.status_code == 200, r1.text
    d1 = r1.json()["decision_id"]

    step2 = _wait_for_step(client, run_id, key)
    assert step2.get("status") == "awaiting_decision"
    assert step2["step_id"] != step1["step_id"]
    r2 = client.post(
        f"/api/v1/runs/{run_id}/steps/{step2['step_id']}/decision",
        json={"idempotency_key": reused, "orders": []},
        headers={"X-API-Key": key},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["decision_id"] != d1, "reused key wrongly replayed step 1"


def test_reaper_frees_session_but_preserves_reads(client):
    """The reaper frees a completed run's heavy engine session (market data) but
    keeps the lightweight ProtocolRun, so step queries, next-step polling, and
    idempotent retries keep working after eviction — no post-eviction regression.
    """
    import dashboard.backend.domain.backtesting.external_run_service as ebs
    import dashboard.backend.domain.runs.service as run_service

    agent_id, key, _ = _new_agent(client)
    version_id = _new_version(client, agent_id, key)
    run_id = _create_run(client, key, version_id)

    # Drive the run to completion with holds; remember the final decision.
    last_step_id = None
    last_idem = None
    last_decision_id = None
    for _ in range(200):
        body = _wait_for_step(client, run_id, key)
        if body.get("status") == "completed":
            break
        last_step_id = body["step_id"]
        last_idem = str(uuid.uuid4())
        r = client.post(
            f"/api/v1/runs/{run_id}/steps/{last_step_id}/decision",
            json={"idempotency_key": last_idem, "orders": []},
            headers={"X-API-Key": key},
        )
        assert r.status_code == 200, r.text
        last_decision_id = r.json()["decision_id"]
    else:
        raise AssertionError("run did not complete")

    run = run_service._runs[run_id]
    bt_id = run.backtest_id
    assert ebs.get_session(bt_id) is not None  # not evicted yet

    reaped = run_service.reap_runs()
    assert reaped >= 1
    # Heavy session freed ...
    assert ebs.get_session(bt_id) is None
    # ... but the ProtocolRun (step maps + idempotency cache) is kept.
    assert run_id in run_service._runs

    # 1) get_step by a known step_id still works (in-memory map preserved).
    s = client.get(
        f"/api/v1/runs/{run_id}/steps/{last_step_id}", headers={"X-API-Key": key}
    )
    assert s.status_code == 200, s.text

    # 2) next-step on a completed run returns "completed", not 409.
    nxt = client.get(f"/api/v1/runs/{run_id}/steps/next", headers={"X-API-Key": key})
    assert nxt.status_code == 200, nxt.text
    assert nxt.json()["status"] == "completed"

    # 3) idempotent retry of the final decision still replays (not 409).
    retry = client.post(
        f"/api/v1/runs/{run_id}/steps/{last_step_id}/decision",
        json={"idempotency_key": last_idem, "orders": []},
        headers={"X-API-Key": key},
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["decision_id"] == last_decision_id

    # 4) DB-backed reads keep working too.
    assert client.get(
        f"/api/v1/runs/{run_id}/result", headers={"X-API-Key": key}
    ).status_code == 200
    status = client.get(f"/api/v1/runs/{run_id}/status", headers={"X-API-Key": key})
    assert status.status_code == 200 and status.json()["status"] == "completed"


def test_late_decision_returns_autoheld_code(client, monkeypatch):
    """Cross-package contract the PyPI SDK's AgentRunner relies on: a decision
    submitted after the step deadline returns a 409 with an 'auto-held' code so
    the SDK can advance instead of aborting the run.

    The backend surfaces the documented `decision_deadline_exceeded` for a
    deadline miss (MEDIUM #8): `submit_decision` consults the engine decision log
    and, when the step was auto-held with decision_source == "timeout_hold",
    raises that code rather than the generic `step_already_finalized` (which is
    reserved for a genuine double-submit of an already-finalized step). The SDK's
    _STEP_AUTOHELD_CODES still tolerates both, so it stays robust either way.
    """
    import dashboard.backend.domain.backtesting.external_run_service as ebs

    agent_id, key, _ = _new_agent(client)
    version_id = _new_version(client, agent_id, key)
    monkeypatch.setattr(ebs, "DECISION_TIMEOUT_SECONDS", 0.2)
    run_id = _create_run(client, key, version_id)
    step = _wait_for_step(client, run_id, key)
    if step.get("status") != "awaiting_decision":
        pytest.skip("run auto-completed before a late decision could be submitted")

    time.sleep(0.5)  # let the step's decision deadline elapse
    resp = client.post(
        f"/api/v1/runs/{run_id}/steps/{step['step_id']}/decision",
        json={"idempotency_key": str(uuid.uuid4()), "orders": []},
        headers={"X-API-Key": key},
    )
    assert resp.status_code == 409, resp.text
    code = resp.json()["detail"]["error"]["code"]
    assert code == "decision_deadline_exceeded", code


def test_reaper_advances_abandoned_run(client, monkeypatch):
    """The reaper drives an abandoned run forward through an elapsed decision
    deadline with no agent polling (each past-due step auto-holds)."""
    import dashboard.backend.domain.backtesting.external_run_service as ebs
    import dashboard.backend.domain.runs.service as run_service

    agent_id, key, _ = _new_agent(client)
    version_id = _new_version(client, agent_id, key)
    monkeypatch.setattr(ebs, "DECISION_TIMEOUT_SECONDS", 0.01)
    run_id = _create_run(client, key, version_id)
    _wait_for_step(client, run_id, key)

    run = run_service._runs[run_id]
    start_index = run.session().step_index

    time.sleep(0.05)  # current step's deadline elapses
    run_service.reap_runs()

    session = run.session()
    # Advanced on its own, or finished and was evicted — either is forward progress.
    assert session is None or session.step_index > start_index


def test_engine_side_rejection_keeps_protocol_order_shape(client):
    """LOW #10 — a rejection produced AFTER the pre-filters (engine batch
    failure or unexecuted-action reconcile) must still carry the protocol
    order shape under ``order``, not the internal engine action dict."""
    agent_id, key, _ = _new_agent(client)
    version_id = _new_version(client, agent_id, key)
    run_id = _create_run(client, key, version_id)
    step = _wait_for_step(client, run_id, key)

    # Selling an unheld symbol passes every pre-filter (caps only constrain
    # buys) and is rejected by the engine, exercising the post-engine path.
    resp = client.post(
        f"/api/v1/runs/{run_id}/steps/{step['step_id']}/decision",
        json={
            "idempotency_key": str(uuid.uuid4()),
            "orders": [{"symbol": "AAPL", "side": "sell", "quantity": 5}],
        },
        headers={"X-API-Key": key},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    rejections = body["validation"]["rejections"]
    assert rejections, body
    for r in rejections:
        order = r["order"]
        # Protocol OrderIn fields, exactly as submitted…
        assert "side" in order and "quantity" in order, order
        assert order["symbol"] == "AAPL"
        # …and none of the engine's internal action-dict fields.
        assert "action" not in order, order
        assert "position_size" not in order, order


def test_agent_version_lookup_is_not_an_existence_oracle(client):
    """LOW #8 — GET /agent-versions/{id} must answer identically for
    "doesn't exist" and "exists but you can't access it", for anonymous,
    garbage-key, and other-agent-key callers alike. A 401/403-vs-404 split
    would let anyone enumerate which version ids exist."""
    agent_id, key, _ = _new_agent(client)
    version_id = _new_version(client, agent_id, key)

    # Anonymous probe: existing and missing ids must be indistinguishable.
    missing = client.get("/api/v1/agent-versions/agv_does_not_exist")
    existing = client.get(f"/api/v1/agent-versions/{version_id}")
    assert missing.status_code == 404
    assert existing.status_code == 404, existing.text

    # Another agent's perfectly valid key: 404, not 403.
    _, other_key, _ = _new_agent(client)
    denied = client.get(
        f"/api/v1/agent-versions/{version_id}", headers={"X-API-Key": other_key}
    )
    assert denied.status_code == 404, denied.text

    # Garbage key: still indistinguishable between existing and missing ids.
    garbage_existing = client.get(
        f"/api/v1/agent-versions/{version_id}", headers={"X-API-Key": "ag_garbage"}
    )
    garbage_missing = client.get(
        "/api/v1/agent-versions/agv_does_not_exist", headers={"X-API-Key": "ag_garbage"}
    )
    assert garbage_existing.status_code == 404, garbage_existing.text
    assert garbage_missing.status_code == 404, garbage_missing.text

    # The legitimate owner still reads it fine.
    ok = client.get(f"/api/v1/agent-versions/{version_id}", headers={"X-API-Key": key})
    assert ok.status_code == 200


def test_observation_features_cover_configured_symbols(client, monkeypatch):
    """LOW #11 — the step observation must include features for EVERY symbol
    the run's config declares tradeable, not a top-10-RSI sample of them (an
    agent constrained to N symbols can't trade what it can't see)."""
    import dashboard.backend.domain.backtesting.external_run_service as ebs

    eleven = ["AAPL", "MSFT", "JPM", "V", "JNJ", "WMT", "PG", "MA", "HD", "DIS", "MCD"]

    def _bars_for(symbols):
        times = []
        for day in ("2026-04-15", "2026-04-16"):
            for hour in (10, 11, 12, 13, 14, 15):
                times.append(ET.localize(pd.Timestamp(f"{day} {hour}:00")))
        idx = pd.DatetimeIndex(times)
        n = len(idx)
        data = {}
        for i, sym in enumerate(symbols):
            closes = [100.0 + 10 * i + j * 0.5 for j in range(n)]
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

    class _ElevenLoader:
        def fetch_bars(self, symbols, start, end):
            return _bars_for(eleven)

    monkeypatch.setattr(ebs, "AlpacaDataLoader", _ElevenLoader)

    agent_id, key, _ = _new_agent(client)
    version_id = _new_version(client, agent_id, key)
    resp = client.post(
        "/api/v1/runs",
        json={
            "agent_version_id": version_id,
            "environment": {"type": "backtest", "environment_id": "us-equity-hourly-v1"},
            "config": {
                "start_date": "2026-04-15",
                "end_date": "2026-04-16",
                "symbols": eleven,
            },
        },
        headers={"X-API-Key": key},
    )
    assert resp.status_code == 200, resp.text
    run_id = resp.json()["run_id"]

    step = _wait_for_step(client, run_id, key)
    features = step["observation"]["market"]["features"]
    assert set(features.keys()) == set(eleven), (
        f"missing features for: {set(eleven) - set(features.keys())}"
    )
