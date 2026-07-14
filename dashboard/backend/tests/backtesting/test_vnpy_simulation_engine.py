"""End-to-end engine coverage for the offline vn.py simulation provider."""

from __future__ import annotations

import subprocess
import sys

from dashboard.backend.domain.backtesting import engine as engine_module
from dashboard.backend.domain.backtesting.engine import HourlyBacktester
from dashboard.backend.infrastructure.llm.validator import DJIA_30
from dashboard.backend.infrastructure.market_data.provider import VNPY_SIMULATION


class RecordingDB:
    def __init__(self):
        self.runs = []
        self.equity_points = []
        self.trades = []

    def insert_run(self, **kwargs):
        self.runs.append(kwargs)

    def insert_equity_points(self, run_id, points):
        self.equity_points.append((run_id, list(points)))

    def insert_trades(self, run_id, trades):
        self.trades.append((run_id, list(trades)))


def fail_llm_client():
    raise AssertionError("simulation mode must not create an LLM client")


def test_simulation_constructor_forces_rule_based_mode(monkeypatch):
    monkeypatch.setenv("ENABLE_VNPY_SIMULATION", "true")
    monkeypatch.setattr(engine_module, "HAS_ANTHROPIC", True)
    monkeypatch.setattr(engine_module, "make_llm_client", fail_llm_client)

    backtester = HourlyBacktester(
        "2026-04-01",
        "2026-04-23",
        use_llm=True,
        data_source=VNPY_SIMULATION,
    )

    assert backtester.data_source == VNPY_SIMULATION
    assert backtester.use_llm is False
    assert backtester.llm_client is None


def test_canonical_simulation_runs_agent_and_both_baselines_offline(monkeypatch):
    monkeypatch.setenv("ENABLE_VNPY_SIMULATION", "true")
    monkeypatch.setattr(engine_module, "HAS_ANTHROPIC", True)
    monkeypatch.setattr(engine_module, "make_llm_client", fail_llm_client)
    recording_db = RecordingDB()
    monkeypatch.setattr(engine_module, "db", recording_db)

    backtester = HourlyBacktester(
        "2026-04-01",
        "2026-04-23",
        session_id="vnpy-sim-test",
        use_llm=True,
        data_source=VNPY_SIMULATION,
    )
    backtester.load_data()
    backtester.calculate_indicators()
    agent_id, agent_curve = backtester.run_agent_backtest()
    buyhold_id, buyhold_curve = backtester.run_buyhold_baseline()
    djia_id, djia_curve = backtester.run_djia_baseline()

    assert set(backtester.all_data) == set(DJIA_30)
    assert agent_id and buyhold_id and djia_id
    assert agent_curve and buyhold_curve and djia_curve
    assert recording_db.trades and recording_db.trades[0][1]
    assert len(recording_db.runs) == 3
    assert {run["metadata"]["data_source"] for run in recording_db.runs} == {
        VNPY_SIMULATION
    }
    agent_run = recording_db.runs[0]
    assert agent_run["llm_model"] == "rule-based"
    assert agent_run["llm_calls"] == 0
    assert agent_run["est_cost_usd"] == 0


def test_cli_exposes_data_source_option():
    result = subprocess.run(
        [sys.executable, "dashboard/scripts/backtest_hourly_agent.py", "--help"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "--data-source" in result.stdout
    assert "vnpy_simulation" in result.stdout
