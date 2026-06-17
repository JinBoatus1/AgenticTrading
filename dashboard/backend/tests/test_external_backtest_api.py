"""Tests for external agent backtest API."""

import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import app
from database import BacktestDatabase
from external_backtest_service import _sessions, get_decision_format, parse_actions_payload


@pytest.fixture
def client(temp_db, monkeypatch):
    import app as app_module
    import database as db_module
    import external_backtest_service as svc

    monkeypatch.setattr(app_module, "db", temp_db)
    monkeypatch.setattr(db_module, "db", temp_db)
    monkeypatch.setattr(svc, "db", temp_db)
    _sessions.clear()
    return TestClient(app)


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    test_db = BacktestDatabase(db_path=db_path)
    yield test_db


def test_decision_schema_endpoint(client):
    resp = client.get("/api/v1/backtest/schema")
    assert resp.status_code == 200
    data = resp.json()
    assert "format" in data
    assert "valid_symbols" in data
    assert len(data["valid_symbols"]) == 30


def test_start_requires_session(client):
    resp = client.post(
        "/api/v1/backtest/start",
        json={"start_date": "2026-04-15", "end_date": "2026-04-16"},
    )
    assert resp.status_code == 400


def test_parse_actions_payload_valid():
    payload = {
        "actions": [{
            "action": "hold",
            "symbol": "AAPL",
            "confidence": 0.5,
            "reasoning": "No signal this hour",
            "position_size": 0,
        }]
    }
    decisions, err = parse_actions_payload(payload)
    assert err is None
    assert len(decisions) == 1


def test_get_decision_format():
    fmt = get_decision_format()
    assert "actions" in fmt
