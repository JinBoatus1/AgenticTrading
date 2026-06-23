"""
Auth API tests using a temporary SQLite database.
"""

import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dashboard.backend.app import app
from dashboard.backend.users import UserStore


@pytest.fixture
def temp_user_store():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = UserStore(db_path=Path(tmpdir) / "auth_test.db")
        yield store


@pytest.fixture
def client(temp_user_store, monkeypatch):
    import dashboard.backend.users as users_module

    monkeypatch.setattr(users_module, "user_store", temp_user_store)
    return TestClient(app)


def test_api_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_signup_login_me_logout_flow(client):
    signup = client.post(
        "/api/auth/signup",
        json={
            "email": "alice@example.com",
            "display_name": "Alice",
            "password": "securepass1",
        },
    )
    assert signup.status_code == 200
    signup_data = signup.json()
    assert signup_data["user"]["email"] == "alice@example.com"
    assert signup_data["user"]["display_name"] == "Alice"
    assert signup_data["user"]["role"] == "user"
    assert "password_hash" not in signup_data["user"]
    assert signup_data["token"]

    duplicate = client.post(
        "/api/auth/signup",
        json={
            "email": "alice@example.com",
            "display_name": "Alice 2",
            "password": "securepass1",
        },
    )
    assert duplicate.status_code == 409

    login = client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": "securepass1"},
    )
    assert login.status_code == 200
    token = login.json()["token"]

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "alice@example.com"

    logout = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout.status_code == 200

    me_after = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_after.status_code == 401


def test_me_requires_auth(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_login_invalid_password(client):
    client.post(
        "/api/auth/signup",
        json={
            "email": "bob@example.com",
            "display_name": "Bob",
            "password": "securepass1",
        },
    )
    response = client.post(
        "/api/auth/login",
        json={"email": "bob@example.com", "password": "wrong-password"},
    )
    assert response.status_code == 401
