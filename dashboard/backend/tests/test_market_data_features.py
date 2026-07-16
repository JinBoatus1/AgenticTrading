"""Feature gating and API propagation for selectable market-data sources."""

from __future__ import annotations

import subprocess
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from dashboard.backend.app import app
import dashboard.backend.api.routers.backtests as backtests
from dashboard.backend.infrastructure.market_data.provider import (
    MarketDataDependencyError,
    VNPY_SIMULATION,
    validate_market_data_source,
)

REAL_RUN_BACKTEST_BACKGROUND = backtests.run_backtest_background


class Spy:
    def __init__(self):
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))


def session_headers():
    return {"X-Session-Id": str(uuid.uuid4())}


@pytest.fixture(autouse=True)
def reset_backtest_state(monkeypatch):
    backtests._backtest_rate_limiter.reset()
    backtests.backtest_status.update(
        {
            "running": False,
            "error": None,
            "runs_count": 0,
            "started_at": None,
            "progress_file": None,
            "live_run_id": None,
        }
    )
    monkeypatch.setattr(backtests, "run_backtest_background", lambda *a, **k: None)
    yield
    backtests._backtest_rate_limiter.reset()


def test_features_endpoint_reports_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_VNPY_SIMULATION", raising=False)

    response = TestClient(app).get("/config/features")

    assert response.status_code == 200
    assert response.json() == {"vnpy_simulation_enabled": False}


def test_features_endpoint_reports_enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_VNPY_SIMULATION", "true")

    response = TestClient(app).get("/config/features")

    assert response.status_code == 200
    assert response.json() == {"vnpy_simulation_enabled": True}


def test_unknown_source_returns_422_before_scheduling(monkeypatch):
    spy = Spy()
    monkeypatch.setattr(backtests, "run_backtest_background", spy)

    response = TestClient(app).post(
        "/backtest/run",
        json={
            "start_date": "2026-04-01",
            "end_date": "2026-04-23",
            "data_source": "unknown",
        },
        headers=session_headers(),
    )

    assert response.status_code == 422
    assert spy.calls == []


def test_disabled_simulation_returns_403_before_scheduling(monkeypatch):
    monkeypatch.delenv("ENABLE_VNPY_SIMULATION", raising=False)
    spy = Spy()
    monkeypatch.setattr(backtests, "run_backtest_background", spy)

    response = TestClient(app).post(
        "/backtest/run",
        json={
            "start_date": "2026-04-01",
            "end_date": "2026-04-23",
            "data_source": VNPY_SIMULATION,
        },
        headers=session_headers(),
    )

    assert response.status_code == 403
    assert spy.calls == []


def test_missing_vnpy_returns_503_before_scheduling(monkeypatch):
    monkeypatch.setenv("ENABLE_VNPY_SIMULATION", "true")
    spy = Spy()
    monkeypatch.setattr(backtests, "run_backtest_background", spy)

    def dependency_error(source):
        raise MarketDataDependencyError(
            "vn.py is not installed; run pip install -r requirements-vnpy.txt"
        )

    monkeypatch.setattr(backtests, "ensure_market_data_source_available", dependency_error)

    response = TestClient(app).post(
        "/backtest/run",
        json={
            "start_date": "2026-04-01",
            "end_date": "2026-04-23",
            "data_source": VNPY_SIMULATION,
        },
        headers=session_headers(),
    )

    assert response.status_code == 503
    assert "requirements-vnpy.txt" in response.text
    assert spy.calls == []


def test_enabled_simulation_is_passed_to_background_runner(monkeypatch):
    monkeypatch.setenv("ENABLE_VNPY_SIMULATION", "true")
    spy = Spy()
    monkeypatch.setattr(backtests, "run_backtest_background", spy)
    # Stand in for "vn.py is installed" without requiring the optional
    # dependency: validate_market_data_source is the real allow-list + feature
    # gate, minus the find_spec probe. The env var above therefore still has to
    # be set for this to reach the runner (test_disabled_... proves the 403),
    # and the probe itself is covered by test_missing_vnpy_returns_503.
    monkeypatch.setattr(
        backtests, "ensure_market_data_source_available", validate_market_data_source
    )

    response = TestClient(app).post(
        "/backtest/run",
        json={
            "start_date": "2026-04-01",
            "end_date": "2026-04-23",
            "data_source": VNPY_SIMULATION,
        },
        headers=session_headers(),
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert len(spy.calls) == 1
    assert spy.calls[0][0][-1] == VNPY_SIMULATION


@pytest.mark.parametrize(
    ("data_source", "expected_flag", "unexpected_flag"),
    [
        ("alpaca", "--use-llm", "--no-llm"),
        (VNPY_SIMULATION, "--no-llm", "--use-llm"),
    ],
)
def test_background_command_uses_correct_llm_flag(
    monkeypatch, data_source, expected_flag, unexpected_flag
):
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(backtests.db, "get_runs_by_mode", lambda mode: [])

    REAL_RUN_BACKTEST_BACKGROUND(
        "2026-04-01",
        "2026-04-23",
        "session-id",
        data_source=data_source,
    )

    command = captured["command"]
    assert command[command.index("--data-source") + 1] == data_source
    assert expected_flag in command
    assert unexpected_flag not in command
