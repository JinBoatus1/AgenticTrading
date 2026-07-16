"""
PostgresUserStore tests.

Two tiers:
1. Dispatch-logic tests (no live Postgres needed) - verify users.py picks
   the right store class based on USERS_DATABASE_URL.
2. Behavioral tests against a real Postgres - skipped unless
   TEST_POSTGRES_URL is set. Point it at a throwaway database, e.g.:
     docker run --rm -e POSTGRES_PASSWORD=test -e POSTGRES_DB=atl_test \
       -p 5433:5432 postgres:16-alpine
     export TEST_POSTGRES_URL=postgresql://postgres:test@localhost:5433/atl_test
"""

import os

import pytest
from fastapi.testclient import TestClient

from dashboard.backend.app import app

TEST_POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")

pg_only = pytest.mark.skipif(
    not TEST_POSTGRES_URL,
    reason="TEST_POSTGRES_URL not set; skipping live-Postgres tests",
)


def test_build_user_store_defaults_to_sqlite(monkeypatch):
    import dashboard.backend.users as users_module

    monkeypatch.delenv("USERS_DATABASE_URL", raising=False)
    store = users_module._build_user_store()
    assert isinstance(store, users_module.UserStore)


def test_build_user_store_picks_postgres_when_url_set(monkeypatch):
    import dashboard.backend.users as users_module
    import dashboard.backend.users_postgres as users_postgres_module

    created = {}

    class FakePostgresUserStore:
        def __init__(self, database_url):
            created["database_url"] = database_url

    monkeypatch.setattr(users_postgres_module, "PostgresUserStore", FakePostgresUserStore)
    monkeypatch.setenv("USERS_DATABASE_URL", "postgresql://fake/db")

    store = users_module._build_user_store()

    assert isinstance(store, FakePostgresUserStore)
    assert created["database_url"] == "postgresql://fake/db"


@pytest.fixture
def temp_postgres_store():
    from dashboard.backend.users_postgres import PostgresUserStore

    store = PostgresUserStore(TEST_POSTGRES_URL)
    with store._get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM auth_sessions")
            cur.execute("DELETE FROM users")
    yield store


@pytest.fixture
def pg_client(temp_postgres_store, monkeypatch):
    import dashboard.backend.api.auth as auth_module
    import dashboard.backend.users as users_module

    monkeypatch.setattr(users_module, "user_store", temp_postgres_store)
    # api/auth.py binds the singleton into its own namespace at import time
    # (`from dashboard.backend.users import user_store`), so patching
    # users_module alone leaves every auth route on the original SQLite
    # store -- which is how this "postgres" test silently exercised SQLite
    # until CI first ran the live tier and it collided with test_auth.py's
    # alice@example.com (409 instead of 200).
    monkeypatch.setattr(auth_module, "user_store", temp_postgres_store)
    return TestClient(app)


@pg_only
def test_signup_login_me_logout_flow_postgres(pg_client, temp_postgres_store):
    signup = pg_client.post(
        "/api/auth/signup",
        json={"email": "alice@example.com", "display_name": "Alice", "password": "securepass1"},
    )
    assert signup.status_code == 200
    signup_data = signup.json()
    assert signup_data["user"]["email"] == "alice@example.com"
    assert signup_data["user"]["display_name"] == "Alice"
    assert signup_data["user"]["role"] == "user"
    assert "password_hash" not in signup_data["user"]
    assert signup_data["token"]

    # Prove the route's write actually landed in Postgres. Without this, a
    # regression that re-detaches the routes from the patched store would
    # leave this test green while testing SQLite -- which is exactly the
    # state it shipped in.
    assert temp_postgres_store.get_user_by_email("alice@example.com") is not None

    duplicate = pg_client.post(
        "/api/auth/signup",
        json={"email": "alice@example.com", "display_name": "Alice 2", "password": "securepass1"},
    )
    assert duplicate.status_code == 409

    login = pg_client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": "securepass1"},
    )
    assert login.status_code == 200
    token = login.json()["token"]

    me = pg_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "alice@example.com"

    logout = pg_client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout.status_code == 200

    me_after = pg_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_after.status_code == 401


@pg_only
def test_login_invalid_password_postgres(pg_client):
    pg_client.post(
        "/api/auth/signup",
        json={"email": "bob@example.com", "display_name": "Bob", "password": "securepass1"},
    )
    response = pg_client.post(
        "/api/auth/login",
        json={"email": "bob@example.com", "password": "wrong-password"},
    )
    assert response.status_code == 401
