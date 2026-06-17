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
