"""Tests for leaderboard API."""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import app
import database as db_module
import services.leaderboard_service as lb_service


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "leaderboard.db"
    test_db = db_module.BacktestDatabase(db_path=db_path)
    monkeypatch.setattr(db_module, "db", test_db)
    monkeypatch.setattr(lb_service, "db", test_db)
    return TestClient(app)


def _seed_leaderboard_runs(db, session_id="leaderboard-contest"):
    start = "2026-04-15"
    end = "2026-05-15"

    db.insert_run(
        run_id="lb_djia_index_20260415_20260515",
        session_id=session_id,
        agent_name="Agentic Trading Lab",
        mode="leaderboard",
        start_date=start,
        end_date=end,
        initial_equity=100000,
        final_equity=105000,
        total_return=0.05,
        sharpe_ratio=1.2,
        max_drawdown=-0.02,
        num_trades=1,
        llm_model="djia_index",
    )
    db.insert_equity_points(
        "lb_djia_index_20260415_20260515",
        [
            {"timestamp": "2026-04-15T14:00:00", "equity": 100000, "cash": 0, "positions_value": 100000},
            {"timestamp": "2026-05-15T20:00:00", "equity": 105000, "cash": 0, "positions_value": 105000},
        ],
    )

    db.insert_run(
        run_id="lb_spy_index_20260415_20260515",
        session_id=session_id,
        agent_name="Agentic Trading Lab",
        mode="leaderboard",
        start_date=start,
        end_date=end,
        initial_equity=100000,
        final_equity=103000,
        total_return=0.03,
        sharpe_ratio=0.9,
        max_drawdown=-0.03,
        num_trades=1,
        llm_model="spy_index",
    )
    db.insert_equity_points(
        "lb_spy_index_20260415_20260515",
        [
            {"timestamp": "2026-04-15T14:00:00", "equity": 100000, "cash": 0, "positions_value": 100000},
            {"timestamp": "2026-05-15T20:00:00", "equity": 103000, "cash": 0, "positions_value": 103000},
        ],
    )


def test_leaderboard_api_returns_baselines(client, monkeypatch):
    _seed_leaderboard_runs(lb_service.db)

    monkeypatch.setattr(
        lb_service,
        "ensure_leaderboard_runs",
        lambda force_refresh=False: {
            "session_id": "leaderboard-contest",
            "start_date": "2026-04-15",
            "end_date": "2026-05-15",
            "created": 0,
            "refreshed_at": "2026-06-18T00:00:00+00:00",
        },
    )

    resp = client.get("/api/v1/leaderboard")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_entries"] == 2
    assert len(body["entries"]) == 2
    names = {e["team_name"] for e in body["entries"]}
    assert names == {"Agentic Trading Lab"}
    models = {e["model"] for e in body["entries"]}
    assert "DJIA" in models
    assert "SPY" in models
    assert body["entries"][0]["rank"] == 1
    assert body["entries"][0]["entry_type"] == "baseline"
    assert "win_loss_ratio" not in body["entries"][0]
