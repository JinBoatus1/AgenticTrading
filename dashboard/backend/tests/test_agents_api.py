"""Tests for registered external agents API."""

import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import app
from agent_store import AgentStore


@pytest.fixture
def client(tmp_path, monkeypatch):
    import agent_store as agent_store_module
    import api.agents as agents_api
    import database as db_module

    db_path = tmp_path / "test.db"
    test_agents = AgentStore(db_path=db_path)
    test_db = db_module.BacktestDatabase(db_path=db_path)
    monkeypatch.setattr(agent_store_module, "agent_store", test_agents)
    monkeypatch.setattr(agents_api, "agent_store", test_agents)
    monkeypatch.setattr(agents_api, "db", test_db)
    monkeypatch.setattr(db_module, "db", test_db)
    return TestClient(app)


def test_create_and_list_agents(client):
    browser_session = str(uuid.uuid4())
    headers = {"X-Session-Id": browser_session}

    created = client.post(
        "/api/v1/agents",
        json={"name": "my-strategy", "model_name": "rsi-demo"},
        headers=headers,
    )
    assert created.status_code == 200
    body = created.json()
    assert body["api_key"].startswith("ag_")
    assert body["session_id"]
    assert body["agent"]["name"] == "my-strategy"

    listed = client.get("/api/v1/agents", headers=headers)
    assert listed.status_code == 200
    agents = listed.json()["agents"]
    assert len(agents) == 1
    assert agents[0]["agent_id"] == body["agent"]["agent_id"]


def test_resolve_api_key(client):
    browser_session = str(uuid.uuid4())
    headers = {"X-Session-Id": browser_session}
    created = client.post(
        "/api/v1/agents",
        json={"name": "resolver-test"},
        headers=headers,
    ).json()

    resolved = client.get(
        "/api/v1/agents/resolve",
        headers={"X-API-Key": created["api_key"]},
    )
    assert resolved.status_code == 200
    data = resolved.json()
    assert data["session_id"] == created["session_id"]
    assert data["name"] == "resolver-test"


def test_resolve_invalid_api_key(client):
    resp = client.get("/api/v1/agents/resolve", headers={"X-API-Key": "ag_invalid"})
    assert resp.status_code == 401


def test_import_session_from_backtest_runs(client):
    browser_session = str(uuid.uuid4())
    headers = {"X-Session-Id": browser_session}

    import database as db_module

    db_module.db.insert_run(
        run_id="ext_test_import",
        session_id=browser_session,
        agent_name="my-strategy",
        mode="backtest",
        start_date="2026-04-15",
        end_date="2026-04-16",
        initial_equity=100000,
        final_equity=101000,
        total_return=0.01,
        sharpe_ratio=0.5,
        max_drawdown=-0.02,
        num_trades=3,
        llm_model="rsi-demo",
    )

    imported = client.post("/api/v1/agents/import-session", json={}, headers=headers)
    assert imported.status_code == 200
    body = imported.json()
    assert body["agent"]["name"] == "my-strategy"
    assert body["agent"]["session_id"] == browser_session

    listed = client.get("/api/v1/agents", headers=headers)
    assert len(listed.json()["agents"]) == 1


def test_claim_account_links_browser_agents(client):
    browser_session = str(uuid.uuid4())
    anon_headers = {"X-Session-Id": browser_session, "X-Browser-Id": browser_session}

    created = client.post(
        "/api/v1/agents",
        json={"name": "pre-login-agent"},
        headers=anon_headers,
    )
    assert created.status_code == 200
    agent_id = created.json()["agent"]["agent_id"]

    signup = client.post(
        "/api/auth/signup",
        json={
            "email": "claim-test@example.com",
            "display_name": "Claim Test",
            "password": "securepass123",
        },
    )
    assert signup.status_code == 200
    token = signup.json()["token"]
    auth_headers = {
        **anon_headers,
        "Authorization": f"Bearer {token}",
    }

    claimed = client.post("/api/v1/agents/claim-account", headers=auth_headers)
    assert claimed.status_code == 200
    body = claimed.json()
    assert body["claimed"] >= 1
    assert any(a["agent_id"] == agent_id for a in body["agents"])

    listed = client.get("/api/v1/agents", headers={"Authorization": f"Bearer {token}"})
    assert listed.status_code == 200
    assert len(listed.json()["agents"]) == 1
    assert listed.json()["agents"][0]["agent_id"] == agent_id


def test_rotate_api_key(client):
    browser_session = str(uuid.uuid4())
    headers = {"X-Session-Id": browser_session, "X-Browser-Id": browser_session}

    created = client.post(
        "/api/v1/agents",
        json={"name": "rotate-me"},
        headers=headers,
    ).json()
    agent_id = created["agent"]["agent_id"]
    old_key = created["api_key"]

    rotated = client.post(f"/api/v1/agents/{agent_id}/rotate-api-key", headers=headers)
    assert rotated.status_code == 200
    new_key = rotated.json()["api_key"]
    assert new_key.startswith("ag_")
    assert new_key != old_key

    assert client.get("/api/v1/agents/resolve", headers={"X-API-Key": old_key}).status_code == 401
    resolved = client.get("/api/v1/agents/resolve", headers={"X-API-Key": new_key})
    assert resolved.status_code == 200
    assert resolved.json()["agent_id"] == agent_id
