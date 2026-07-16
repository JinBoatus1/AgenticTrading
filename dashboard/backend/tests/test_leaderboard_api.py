"""Tests for leaderboard API."""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dashboard.backend.app import app
import dashboard.backend.database as db_module
import dashboard.backend.domain.leaderboard.service as lb_service


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
        lambda force_refresh=False, period="contest", config=None: {
            "session_id": "leaderboard-contest",
            "start_date": "2026-04-15",
            "end_date": "2026-05-15",
            "period": "contest",
            "created": 0,
            "refreshed_at": "2026-06-18T00:00:00+00:00",
        },
    )

    resp = client.get("/api/v1/leaderboard")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_entries"] == 2
    assert body["period"] == "contest"
    assert body["phase_label"] == "Preseason"
    assert len(body["entries"]) == 2
    names = {e["team_name"] for e in body["entries"]}
    assert names == {"Agentic Trading Lab"}
    models = {e["model"] for e in body["entries"]}
    assert "DJIA" in models
    assert "SPY" in models
    assert body["entries"][0]["rank"] == 1
    assert body["entries"][0]["entry_type"] == "baseline"


def test_daily_leaderboard_api_uses_daily_window(client, monkeypatch):
    day = "2026-07-14"  # Tuesday
    monkeypatch.setattr(lb_service, "daily_window_dates", lambda as_of=None: (day, day))

    start = day
    end = day
    for strategy_id, final, ret, sharpe in (
        ("djia_index", 101000, 0.01, 0.5),
        ("spy_index", 100500, 0.005, 0.4),
    ):
        run_id = f"lb_{strategy_id}_{start.replace('-', '')}_{end.replace('-', '')}"
        lb_service.db.insert_run(
            run_id=run_id,
            session_id="leaderboard-daily",
            agent_name="Agentic Trading Lab",
            mode="leaderboard",
            start_date=start,
            end_date=end,
            initial_equity=100000,
            final_equity=final,
            total_return=ret,
            sharpe_ratio=sharpe,
            max_drawdown=-0.01,
            num_trades=1,
            llm_model=strategy_id,
        )
        lb_service.db.insert_equity_points(
            run_id,
            [
                {"timestamp": f"{start}T14:00:00", "equity": 100000, "cash": 0, "positions_value": 100000},
                {"timestamp": f"{end}T20:00:00", "equity": final, "cash": 0, "positions_value": final},
            ],
        )

    monkeypatch.setattr(
        lb_service,
        "ensure_leaderboard_runs",
        lambda force_refresh=False, period="contest", config=None: {
            "session_id": "leaderboard-daily",
            "start_date": day,
            "end_date": day,
            "period": "daily",
            "created": 0,
            "refreshed_at": "2026-07-15T00:00:00+00:00",
        },
    )

    resp = client.get("/api/v1/leaderboard?period=daily")
    assert resp.status_code == 200
    body = resp.json()
    assert body["period"] == "daily"
    assert body["phase_label"] == "Daily"
    assert body["standings_label"] == "Daily Standings"
    assert body["window"]["start_date"] == day
    assert body["window"]["end_date"] == day
    assert body["total_entries"] == 2
    assert body["entries"][0]["rank"] == 1


def test_daily_window_dates_skips_weekend():
    # Monday → previous Friday
    from datetime import date

    start, end = lb_service.daily_window_dates(as_of=date(2026, 7, 13))  # Monday
    assert start == end == "2026-07-10"
    # Tuesday → Monday
    start, end = lb_service.daily_window_dates(as_of=date(2026, 7, 14))
    assert start == end == "2026-07-13"
