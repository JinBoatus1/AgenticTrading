"""Portfolio allocate / reclaim / delete-returns (#175)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dashboard.backend.app import app
from dashboard.backend.domain.agents.repository import AgentStore
from dashboard.backend.domain.backtesting.constants import (
    DEFAULT_AGENT_CASH_ALLOCATION,
    DEFAULT_PORTFOLIO_EQUITY,
    MAX_AGENT_CASH_ALLOCATION,
)
from dashboard.backend.domain.portfolios.repository import PortfolioStore
from dashboard.backend.users import UserStore


@pytest.fixture
def client(monkeypatch):
    """Auth + portfolio + agents share one content DB (ledger ↔ sleeve)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        user_store = UserStore(db_path=root / "users.db")
        content_db = root / "content.db"
        portfolio_store = PortfolioStore(db_path=content_db)
        agent_store = AgentStore(db_path=content_db)

        import dashboard.backend.users as users_module
        import dashboard.backend.api.auth as auth_module
        import dashboard.backend.domain.portfolios.repository as portfolio_repo
        import dashboard.backend.domain.portfolios.service as portfolio_service_module
        import dashboard.backend.domain.agents.repository as agent_repo
        import dashboard.backend.domain.agents.service as agent_service_module

        monkeypatch.setattr(users_module, "user_store", user_store)
        # auth.py binds user_store at import time — patch that name too.
        monkeypatch.setattr(auth_module, "user_store", user_store)
        monkeypatch.setattr(portfolio_repo, "portfolio_store", portfolio_store)
        monkeypatch.setattr(portfolio_service_module, "portfolio_store", portfolio_store)
        monkeypatch.setattr(agent_repo, "agent_store", agent_store)
        monkeypatch.setattr(agent_service_module.agent_service, "agents", agent_store)
        yield TestClient(app)


def _signup(client: TestClient, email: str = "alloc@example.com") -> tuple[str, dict]:
    resp = client.post(
        "/api/auth/signup",
        json={
            "email": email,
            "display_name": "Alloc User",
            "password": "securepass1",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    return data["token"], data["user"]


def _auth(token: str, browser: str = "browser-alloc-1") -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "X-Browser-Id": browser,
        "X-Session-Id": browser,
    }


def test_create_agent_debits_portfolio(client):
    token, _ = _signup(client)
    headers = _auth(token)

    before = client.get("/api/v1/portfolio", headers=headers).json()["portfolio"]
    assert before["cash_available"] == float(DEFAULT_PORTFOLIO_EQUITY)

    created = client.post(
        "/api/v1/agents",
        headers=headers,
        json={
            "name": "Funded",
            "model_name": "local-model",
            "agent_type": "builtin",
            "cash_allocation": 2500,
        },
    )
    assert created.status_code == 200, created.text
    agent = created.json()["agent"]
    assert agent["cash_allocation"] == 2500

    after = client.get("/api/v1/portfolio", headers=headers).json()["portfolio"]
    assert after["cash_available"] == float(DEFAULT_PORTFOLIO_EQUITY) - 2500
    assert after["allocated"] == 2500


def test_allocate_and_reclaim_endpoints(client):
    token, _ = _signup(client, email="xfer@example.com")
    headers = _auth(token)

    created = client.post(
        "/api/v1/agents",
        headers=headers,
        json={
            "name": "Xfer",
            "model_name": "local-model",
            "agent_type": "builtin",
            "cash_allocation": 0,
        },
    )
    assert created.status_code == 200, created.text
    agent_id = created.json()["agent"]["agent_id"]

    alloc = client.post(
        "/api/v1/portfolio/allocate",
        headers=headers,
        json={"agent_id": agent_id, "amount": 1500},
    )
    assert alloc.status_code == 200, alloc.text
    assert alloc.json()["portfolio"]["cash_available"] == float(DEFAULT_PORTFOLIO_EQUITY) - 1500
    assert alloc.json()["agent"]["cash_allocation"] == 1500

    reclaim = client.post(
        "/api/v1/portfolio/reclaim",
        headers=headers,
        json={"agent_id": agent_id, "amount": 500},
    )
    assert reclaim.status_code == 200, reclaim.text
    assert reclaim.json()["portfolio"]["cash_available"] == float(DEFAULT_PORTFOLIO_EQUITY) - 1000
    assert reclaim.json()["agent"]["cash_allocation"] == 1000


def test_allocate_blocked_when_insufficient_cash(client):
    token, _ = _signup(client, email="poor@example.com")
    headers = _auth(token)

    # Drain most of the $10k ledger with maxed sleeves ($3k each).
    for i in range(3):
        filled = client.post(
            "/api/v1/agents",
            headers=headers,
            json={
                "name": f"Drain{i}",
                "model_name": "local-model",
                "cash_allocation": float(MAX_AGENT_CASH_ALLOCATION),
            },
        )
        assert filled.status_code == 200, filled.text

    created = client.post(
        "/api/v1/agents",
        headers=headers,
        json={"name": "A", "model_name": "local-model", "cash_allocation": 0},
    )
    agent_id = created.json()["agent"]["agent_id"]

    # Remaining unallocated is $1,000; request is within the per-agent max but
    # still more than cash available → business-rule 400 (not pydantic 422).
    too_much = client.post(
        "/api/v1/portfolio/allocate",
        headers=headers,
        json={"agent_id": agent_id, "amount": float(MAX_AGENT_CASH_ALLOCATION)},
    )
    assert too_much.status_code == 400


def test_delete_agent_returns_funds(client):
    token, _ = _signup(client, email="del@example.com")
    headers = _auth(token)
    created = client.post(
        "/api/v1/agents",
        headers=headers,
        json={
            "name": "Temp",
            "model_name": "local-model",
            "agent_type": "builtin",
            "cash_allocation": float(DEFAULT_AGENT_CASH_ALLOCATION),
        },
    )
    assert created.status_code == 200, created.text
    agent_id = created.json()["agent"]["agent_id"]

    mid = client.get("/api/v1/portfolio", headers=headers).json()["portfolio"]
    assert mid["cash_available"] == float(DEFAULT_PORTFOLIO_EQUITY) - float(
        DEFAULT_AGENT_CASH_ALLOCATION
    )

    deleted = client.delete(f"/api/v1/agents/{agent_id}", headers=headers)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["reclaimed"] == float(DEFAULT_AGENT_CASH_ALLOCATION)

    after = client.get("/api/v1/portfolio", headers=headers).json()["portfolio"]
    assert after["cash_available"] == float(DEFAULT_PORTFOLIO_EQUITY)
    assert after["allocated"] == 0.0


def test_patch_cash_allocation_moves_ledger(client):
    token, _ = _signup(client, email="patch@example.com")
    headers = _auth(token)
    created = client.post(
        "/api/v1/agents",
        headers=headers,
        json={"name": "P", "model_name": "local-model", "cash_allocation": 1000},
    )
    agent_id = created.json()["agent"]["agent_id"]

    up = client.patch(
        f"/api/v1/agents/{agent_id}",
        headers=headers,
        json={"cash_allocation": 3000},
    )
    assert up.status_code == 200, up.text
    assert up.json()["agent"]["cash_allocation"] == 3000
    pf = client.get("/api/v1/portfolio", headers=headers).json()["portfolio"]
    assert pf["cash_available"] == float(DEFAULT_PORTFOLIO_EQUITY) - 3000

    down = client.patch(
        f"/api/v1/agents/{agent_id}",
        headers=headers,
        json={"cash_allocation": 500},
    )
    assert down.status_code == 200, down.text
    pf2 = client.get("/api/v1/portfolio", headers=headers).json()["portfolio"]
    assert pf2["cash_available"] == float(DEFAULT_PORTFOLIO_EQUITY) - 500
