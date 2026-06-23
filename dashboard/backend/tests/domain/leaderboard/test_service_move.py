"""Phase 3C3 — leaderboard service move + characterization.

Verifies the leaderboard service/baselines moved to the canonical
``dashboard.backend.domain.leaderboard`` package while the old modules remain
re-export shims, and characterizes ranking, tie ordering, result schema, metric
preservation, and the contest-window helpers against isolated storage.
"""

import ast
from pathlib import Path

import pytest

from dashboard.backend import services as _services  # noqa: F401
from dashboard.backend.database import BacktestDatabase
from dashboard.backend.domain.leaderboard import baselines as canon_baselines
from dashboard.backend.domain.leaderboard import service as canon_service
from dashboard.backend.engines import leaderboard_baselines as baselines_shim
from dashboard.backend.services import leaderboard_service as service_shim

_PUBLIC_SERVICE = [
    "LEADERBOARD_MODE",
    "load_leaderboard_config",
    "ensure_leaderboard_runs",
    "deploy_model_run",
    "get_leaderboard",
]
_PUBLIC_BASELINES = ["fetch_hourly_bars", "compute_equity_curve", "calc_metrics", "downsample_daily"]


# ---------------------------------------------------------------------------
# Canonical imports + old-path identity
# ---------------------------------------------------------------------------

def test_canonical_modules_import():
    assert canon_service.get_leaderboard.__module__ == (
        "dashboard.backend.domain.leaderboard.service"
    )
    assert canon_baselines.calc_metrics.__module__ == (
        "dashboard.backend.domain.leaderboard.baselines"
    )


def test_service_shim_reexports_identical_objects():
    for name in _PUBLIC_SERVICE:
        assert getattr(service_shim, name) is getattr(canon_service, name), name


def test_baselines_shim_reexports_identical_objects():
    for name in _PUBLIC_BASELINES:
        assert getattr(baselines_shim, name) is getattr(canon_baselines, name), name
    assert baselines_shim.INITIAL_CAPITAL == canon_baselines.INITIAL_CAPITAL


def test_service_wires_canonical_baselines():
    # The service composes the canonical baseline helpers (no duplication).
    assert canon_service.calc_metrics is canon_baselines.calc_metrics
    assert canon_service.fetch_hourly_bars is canon_baselines.fetch_hourly_bars
    assert canon_service.downsample_daily is canon_baselines.downsample_daily


# ---------------------------------------------------------------------------
# Import boundary: no API / scripts / frontend imports
# ---------------------------------------------------------------------------

def _imported_modules(path: Path):
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
    return mods


def test_canonical_package_does_not_import_api_or_scripts():
    package_dir = Path(canon_service.__file__).parent
    for py in package_dir.rglob("*.py"):
        mods = _imported_modules(py)
        for m in mods:
            assert not m.startswith("dashboard.backend.api"), (py.name, m)
            assert not m.startswith("dashboard.scripts"), (py.name, m)
            assert m != "fastapi" and not m.startswith("fastapi."), (py.name, m)


def test_runtime_consumer_uses_canonical_import():
    import dashboard.backend.api.leaderboard as api_lb
    mods = _imported_modules(api_lb.__file__)
    assert "dashboard.backend.domain.leaderboard.service" in mods
    assert "dashboard.backend.services.leaderboard_service" not in mods


# ---------------------------------------------------------------------------
# Ranking + tie ordering (pure function)
# ---------------------------------------------------------------------------

def test_rank_entries_orders_and_breaks_ties_by_return():
    entries = [
        {"entry_id": "A", "cumulative_return": 0.10, "sharpe_ratio": 1.0},
        {"entry_id": "B", "cumulative_return": 0.05, "sharpe_ratio": 2.0},
        {"entry_id": "C", "cumulative_return": 0.01, "sharpe_ratio": 0.5},
    ]
    ranked = canon_service._rank_entries(entries)
    by_id = {e["entry_id"]: e for e in ranked}

    # A and B tie on final_score (1.5); A wins the tie on higher cumulative_return.
    assert by_id["A"]["final_score"] == 1.5
    assert by_id["B"]["final_score"] == 1.5
    assert by_id["A"]["rank"] == 1
    assert by_id["B"]["rank"] == 2
    assert by_id["C"]["rank"] == 3
    assert by_id["A"]["rank_cr"] == 1 and by_id["A"]["rank_sr"] == 2
    assert by_id["B"]["rank_cr"] == 2 and by_id["B"]["rank_sr"] == 1


def test_rank_entries_empty():
    assert canon_service._rank_entries([]) == []


# ---------------------------------------------------------------------------
# get_leaderboard end-to-end against isolated DB + controlled config
# ---------------------------------------------------------------------------

_CONFIG = {
    "session_id": "lb-test",
    "start_date": "2026-04-15",
    "end_date": "2026-05-15",
    "description": "Test contest",
    "initial_capital": 100000,
    "strategies": [
        {"id": "djia_index", "name": "DJIA", "label": "Baseline", "model": "DJIA", "strategy": "market_index"},
        {"id": "spy_index", "name": "SPY", "label": "Baseline", "model": "SPY", "strategy": "market_index"},
    ],
}


@pytest.fixture
def isolated_service(tmp_path, monkeypatch):
    test_db = BacktestDatabase(db_path=tmp_path / "lb.db")
    monkeypatch.setattr(canon_service, "db", test_db)
    monkeypatch.setattr(canon_service, "load_leaderboard_config", lambda: dict(_CONFIG))
    monkeypatch.setattr(
        canon_service,
        "ensure_leaderboard_runs",
        lambda force_refresh=False: {
            "session_id": _CONFIG["session_id"],
            "start_date": _CONFIG["start_date"],
            "end_date": _CONFIG["end_date"],
            "created": 0,
            "refreshed_at": "2026-06-18T00:00:00+00:00",
        },
    )
    return test_db


def _seed(db, strategy_id, total_return, sharpe):
    run_id = f"lb_{strategy_id}_20260415_20260515"
    db.insert_run(
        run_id=run_id,
        session_id=_CONFIG["session_id"],
        agent_name=strategy_id.upper(),
        mode="leaderboard",
        start_date=_CONFIG["start_date"],
        end_date=_CONFIG["end_date"],
        initial_equity=100000,
        final_equity=100000 * (1 + total_return),
        total_return=total_return,
        sharpe_ratio=sharpe,
        max_drawdown=-0.02,
        num_trades=1,
        llm_model=strategy_id,
    )
    db.insert_equity_points(
        run_id,
        [
            {"timestamp": "2026-04-15T14:00:00", "equity": 100000, "cash": 0, "positions_value": 100000},
            {"timestamp": "2026-05-15T20:00:00", "equity": 100000 * (1 + total_return), "cash": 0, "positions_value": 100000 * (1 + total_return)},
        ],
    )


def test_get_leaderboard_schema_and_ranking(isolated_service):
    _seed(isolated_service, "djia_index", 0.05, 1.2)
    _seed(isolated_service, "spy_index", 0.03, 0.9)

    result = canon_service.get_leaderboard()
    assert set(result.keys()) == {"window", "updated_at", "total_entries", "leader", "entries"}
    assert result["total_entries"] == 2
    assert result["window"]["label"] == "2026-04-15 → 2026-05-15"

    entries = result["entries"]
    # djia_index has higher return and sharpe → rank 1.
    assert entries[0]["entry_id"] == "djia_index"
    assert entries[0]["rank"] == 1
    assert result["leader"] == "DJIA_INDEX"

    entry = entries[0]
    expected_fields = {
        "entry_id", "team_name", "team_badge", "model", "entry_type", "is_model",
        "initial_equity", "portfolio_value", "cumulative_return", "sharpe_ratio",
        "max_drawdown", "status", "run_id", "llm_calls", "input_tokens",
        "output_tokens", "est_cost_usd", "equity_curve", "rank_cr", "rank_sr",
        "final_score", "rank",
    }
    assert expected_fields.issubset(set(entry.keys()))
    assert "win_loss_ratio" not in entry
    assert entry["entry_type"] == "baseline"
    assert entry["cumulative_return"] == 0.05
    assert isinstance(entry["equity_curve"], list)


def test_get_leaderboard_skips_uncached_strategies(isolated_service):
    # Only one of the two configured strategies has a cached run.
    _seed(isolated_service, "djia_index", 0.05, 1.2)
    result = canon_service.get_leaderboard()
    assert result["total_entries"] == 1
    assert result["entries"][0]["entry_id"] == "djia_index"
