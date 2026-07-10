"""Tests for /api/discord integration routes (isolated router)."""

import tempfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dashboard.backend.api.routers.discord_integration import router as discord_router
from dashboard.backend.integrations.discord_store import DiscordStore


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = tmp_path / "discord_api.db"
    monkeypatch.setenv("DISCORD_BOT_SERVICE_TOKEN", "test-service-token")
    from dashboard.backend.integrations import discord_store as ds_mod

    ds_mod.discord_store = DiscordStore(db_path=db)
    app = FastAPI()
    app.include_router(discord_router, prefix="/api")
    return TestClient(app)


def _svc_headers():
    return {"X-Discord-Service-Token": "test-service-token"}


def test_connect_token_and_account_status(client):
    r = client.post(
        "/api/discord/connect-token",
        json={"discord_user_id": "999", "discord_username": "u"},
        headers=_svc_headers(),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["linked"] is False
    assert "connect-discord?code=" in body["connect_url"]

    status = client.get("/api/discord/accounts/999", headers=_svc_headers())
    assert status.status_code == 200
    assert status.json()["linked"] is False


def test_agents_requires_link(client):
    r = client.get("/api/discord/agents/999", headers=_svc_headers())
    assert r.status_code == 403


def test_service_token_rejected(client):
    r = client.get("/api/discord/accounts/1", headers={"X-Discord-Service-Token": "wrong"})
    assert r.status_code == 401
