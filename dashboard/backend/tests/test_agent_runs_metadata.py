"""agent_runs.metadata column + effective LLM_MAX_OUTPUT_TOKENS recording.

LOW-sweep residual (PR #67): the per-request output-token ceiling is an env
knob (LLM_MAX_OUTPUT_TOKENS) that changes a run's spend and behavior, but no
row recorded which value was in effect. agent_runs gains a JSON metadata
column (config snapshot, additive) and the engine's LLM-driven agent run
records its effective cap there.
"""

import sqlite3

import pytest

from dashboard.backend.database import BacktestDatabase


def _make_db(tmp_path, name="meta.db"):
    return BacktestDatabase(tmp_path / name)


def _insert_minimal(db, run_id, metadata=None):
    db.insert_run(
        run_id=run_id,
        session_id="meta-session",
        agent_name="meta-agent",
        mode="backtest",
        start_date="2026-01-01",
        end_date="2026-01-31",
        initial_equity=100000.0,
        metadata=metadata,
    )


def test_insert_run_roundtrips_metadata(tmp_path):
    db = _make_db(tmp_path)
    _insert_minimal(db, "run_meta_1", metadata={"llm_max_output_tokens": 600})
    run = db.get_run("run_meta_1")
    assert run["metadata"] == {"llm_max_output_tokens": 600}


def test_metadata_defaults_to_none(tmp_path):
    db = _make_db(tmp_path)
    _insert_minimal(db, "run_meta_2")
    assert db.get_run("run_meta_2")["metadata"] is None


def test_session_listings_parse_metadata_consistently(tmp_path):
    """SELECT * picks the new column up in the list readers too — they must
    return the same parsed shape as get_run, not raw JSON text."""
    db = _make_db(tmp_path)
    _insert_minimal(db, "run_meta_3", metadata={"llm_max_output_tokens": 1234})
    by_session = db.get_runs_by_session("meta-session")
    assert by_session[0]["metadata"] == {"llm_max_output_tokens": 1234}
    grouped = db.get_runs_by_sessions(["meta-session"])
    assert grouped["meta-session"][0]["metadata"] == {"llm_max_output_tokens": 1234}


def test_data_source_provenance_roundtrips_for_api_projection(tmp_path):
    db = _make_db(tmp_path)
    _insert_minimal(
        db,
        "run_vnpy_source",
        metadata={"data_source": "vnpy_simulation"},
    )

    assert db.get_run("run_vnpy_source")["metadata"]["data_source"] == (
        "vnpy_simulation"
    )


def test_migration_adds_metadata_column(tmp_path):
    """A DB created before the column must gain it on open (both
    _init_schema's CREATE IF NOT EXISTS and _migrate_schema must know it)."""
    path = tmp_path / "old.db"
    conn = sqlite3.connect(str(path))
    conn.execute(
        """
        CREATE TABLE agent_runs (
            run_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            agent_name TEXT NOT NULL,
            mode TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            initial_equity REAL NOT NULL,
            final_equity REAL,
            total_return REAL,
            sharpe_ratio REAL,
            max_drawdown REAL,
            num_trades INTEGER DEFAULT 0,
            llm_calls INTEGER DEFAULT 0,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            est_cost_usd REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    conn.close()

    db = BacktestDatabase(path)
    conn = sqlite3.connect(str(path))
    cols = {row[1] for row in conn.execute("PRAGMA table_info(agent_runs)")}
    conn.close()
    assert "metadata" in cols
    _insert_minimal(db, "run_meta_migrated", metadata={"llm_max_output_tokens": 2000})
    assert db.get_run("run_meta_migrated")["metadata"] == {
        "llm_max_output_tokens": 2000
    }


def test_engine_llm_run_metadata_snapshot(monkeypatch):
    """The engine's agent run records the EFFECTIVE cap (whatever the env
    parse produced), while every run records data provenance."""
    import dashboard.backend.domain.backtesting.engine as engine_mod
    from dashboard.backend.domain.backtesting.engine import HourlyBacktester

    backtester = HourlyBacktester.__new__(HourlyBacktester)  # skip creds init
    # _llm_run_metadata() also reads the post-trade/pipeline attrs (added in the
    # post-trade-analysis work); __init__ sets them, but __new__ skips it, so set
    # the no-pipeline defaults here to keep this a pure llm_max_output_tokens test.
    backtester.prompt_adaptations = []
    backtester.initial_pipeline = None
    backtester.pipeline = None
    monkeypatch.setattr(engine_mod.llm_harness, "DEFAULT_MAX_OUTPUT_TOKENS", 777)
    backtester.data_source = "alpaca"

    backtester.use_llm = True
    assert backtester._run_metadata() == {
        "data_source": "alpaca",
        "llm_max_output_tokens": 777,
    }
    backtester.use_llm = False
    assert backtester._run_metadata() == {"data_source": "alpaca"}


def test_engine_agent_run_wires_the_metadata():
    """Wiring guard: the agent-run insert (the LLM one, not the baselines)
    passes the metadata snapshot."""
    from pathlib import Path

    engine_src = (
        Path(__file__).resolve().parents[1]
        / "domain" / "backtesting" / "engine.py"
    ).read_text(encoding="utf-8")
    assert "metadata=self._run_metadata()" in engine_src
