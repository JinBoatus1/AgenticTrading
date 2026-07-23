"""Portfolio store + GET /api/v1/portfolio (#174)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dashboard.backend.app import app
from dashboard.backend.domain.backtesting.constants import DEFAULT_PORTFOLIO_EQUITY
from dashboard.backend.domain.portfolios.repository import PortfolioStore
from dashboard.backend.users import UserStore


@pytest.fixture
def temp_stores(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        user_store = UserStore(db_path=root / "users.db")
        portfolio_store = PortfolioStore(db_path=root / "content.db")

        import dashboard.backend.users as users_module
        import dashboard.backend.domain.portfolios.repository as portfolio_repo
        import dashboard.backend.domain.portfolios.service as portfolio_service_module

        monkeypatch.setattr(users_module, "user_store", user_store)
        monkeypatch.setattr(portfolio_repo, "portfolio_store", portfolio_store)
        monkeypatch.setattr(portfolio_service_module, "portfolio_store", portfolio_store)
        yield user_store, portfolio_store


@pytest.fixture
def client(temp_stores):
    return TestClient(app)


def _signup(client: TestClient, email: str = "pf@example.com") -> str:
    resp = client.post(
        "/api/auth/signup",
        json={
            "email": email,
            "display_name": "PF User",
            "password": "securepass1",
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


def test_build_portfolio_store_defaults_to_sqlite(monkeypatch, capsys):
    import dashboard.backend.domain.portfolios.repository as repo_module

    monkeypatch.delenv("CONTENT_DATABASE_URL", raising=False)
    store = repo_module._build_portfolio_store()
    assert isinstance(store, repo_module.PortfolioStore)
    assert "portfolio_store backend: sqlite (ephemeral on Render)" in capsys.readouterr().out


def test_build_portfolio_store_picks_postgres_when_url_set(monkeypatch, capsys):
    import dashboard.backend.domain.portfolios.repository as repo_module

    created = {}

    class FakePostgresPortfolioStore:
        def __init__(self, database_url):
            created["database_url"] = database_url

    monkeypatch.setenv("CONTENT_DATABASE_URL", "postgresql://u:p@host/db")
    monkeypatch.setattr(
        "dashboard.backend.domain.portfolios.repository_postgres.PostgresPortfolioStore",
        FakePostgresPortfolioStore,
    )
    store = repo_module._build_portfolio_store()
    assert isinstance(store, FakePostgresPortfolioStore)
    assert created["database_url"] == "postgresql://u:p@host/db"
    assert "portfolio_store backend: postgres" in capsys.readouterr().out


def test_get_or_create_bootstraps_10k_and_is_idempotent(temp_stores):
    _, store = temp_stores
    first = store.get_or_create(7)
    assert first["owner_user_id"] == 7
    assert first["equity"] == float(DEFAULT_PORTFOLIO_EQUITY)
    assert first["cash_available"] == float(DEFAULT_PORTFOLIO_EQUITY)
    assert first["allocated"] == 0.0

    second = store.get_or_create(7)
    assert second == first


def test_portfolio_requires_auth(client):
    assert client.get("/api/v1/portfolio").status_code == 401


def test_portfolio_get_bootstraps_for_signed_in_user(client):
    token = _signup(client)
    headers = {"Authorization": f"Bearer {token}"}

    first = client.get("/api/v1/portfolio", headers=headers)
    assert first.status_code == 200, first.text
    body = first.json()["portfolio"]
    assert body["equity"] == float(DEFAULT_PORTFOLIO_EQUITY)
    assert body["cash_available"] == float(DEFAULT_PORTFOLIO_EQUITY)
    assert body["allocated"] == 0.0
    assert body["owner_user_id"]

    second = client.get("/api/v1/portfolio", headers=headers)
    assert second.status_code == 200
    assert second.json()["portfolio"] == body
