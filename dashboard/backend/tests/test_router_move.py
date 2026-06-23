"""Phase 3A3 / 3B3 / 3C2 — HTTP router move verification.

Confirms the agent, run, environment, external-backtest, and algo HTTP routers
moved to the canonical ``dashboard.backend.api.routers`` package while the old
modules remain thin re-export shims, with identical route registration and no
duplicate routes.
"""

import ast
import subprocess
import sys
from pathlib import Path

from fastapi.routing import APIRoute

from dashboard.backend.api import agent_versions as versions_shim
from dashboard.backend.api import agents as agents_shim
from dashboard.backend.api import algo as algo_shim
from dashboard.backend.api import dependencies as deps
from dashboard.backend.api import environments as environments_shim
from dashboard.backend.api import external_backtest as external_backtest_shim
from dashboard.backend.api import leaderboard as leaderboard_shim
from dashboard.backend.api import protocol_auth
from dashboard.backend.api import router as router_module
from dashboard.backend.api import runs as runs_shim
from dashboard.backend.api.routers import agent_versions as versions_canon
from dashboard.backend.api.routers import agents as agents_canon
from dashboard.backend.api.routers import algo as algo_canon
from dashboard.backend.api.routers import environments as environments_canon
from dashboard.backend.api.routers import external_backtest as external_backtest_canon
from dashboard.backend.api.routers import leaderboard as leaderboard_canon
from dashboard.backend.api.routers import runs as runs_canon
from dashboard.backend.app import app

_REPO_ROOT = Path(__file__).resolve().parents[3]

# (method, full path, endpoint name) — the contract that must not change.
EXPECTED_AGENT_ROUTES = {
    ("POST", "/v1/agents", "create_agent"),
    ("GET", "/v1/agents", "list_agents"),
    ("POST", "/v1/agents/claim-account", "claim_account_agents"),
    ("POST", "/v1/agents/import-session", "import_session_agent"),
    ("GET", "/v1/agents/resolve", "resolve_api_key"),
    ("GET", "/v1/agents/{agent_id}/runs", "list_agent_runs"),
    ("GET", "/v1/agents/{agent_id}", "get_agent"),
    ("DELETE", "/v1/agents/{agent_id}", "delete_agent"),
    ("POST", "/v1/agents/{agent_id}/rotate-api-key", "rotate_agent_api_key"),
    ("POST", "/v1/agents/{agent_id}/activate", "activate_agent"),
}

EXPECTED_VERSION_ROUTES = {
    ("POST", "/v1/agents/{agent_id}/versions", "create_agent_version"),
    ("GET", "/v1/agents/{agent_id}/versions", "list_agent_versions"),
    ("GET", "/v1/agent-versions/{agent_version_id}", "get_agent_version"),
}

EXPECTED_RUN_ROUTES = {
    ("POST", "/v1/runs", "create_run"),
    ("GET", "/v1/runs/{run_id}", "get_run"),
    ("GET", "/v1/runs/{run_id}/status", "get_run_status"),
    ("GET", "/v1/runs/{run_id}/steps/next", "get_next_step"),
    ("GET", "/v1/runs/{run_id}/steps/{step_id}", "get_step"),
    ("POST", "/v1/runs/{run_id}/steps/{step_id}/decision", "submit_step_decision"),
    ("GET", "/v1/runs/{run_id}/steps", "list_steps"),
    ("GET", "/v1/runs/{run_id}/decisions", "list_decisions"),
    ("GET", "/v1/runs/{run_id}/trades", "list_trades"),
    ("GET", "/v1/runs/{run_id}/metrics", "get_metrics"),
    ("GET", "/v1/runs/{run_id}/result", "get_result"),
}

EXPECTED_ENV_ROUTES = {
    ("GET", "/v1/environments", "api_list_environments"),
    ("GET", "/v1/environments/{environment_id}", "api_get_environment"),
}

EXPECTED_EXTERNAL_BACKTEST_ROUTES = {
    ("GET", "/v1/backtest/schema", "api_decision_schema"),
    ("POST", "/v1/backtest/start", "api_start_backtest"),
    ("GET", "/v1/backtest/runs/{run_id}/result", "api_run_result"),
    ("GET", "/v1/backtest/runs/{run_id}/trades", "api_run_trades"),
    ("GET", "/v1/backtest/runs/{run_id}/decisions", "api_run_decisions"),
    ("GET", "/v1/backtest/{backtest_id}/status", "api_backtest_status"),
    ("GET", "/v1/backtest/{backtest_id}/decisions", "api_backtest_decisions"),
    ("GET", "/v1/backtest/{backtest_id}/steps/current", "api_get_current_step"),
    ("POST", "/v1/backtest/{backtest_id}/steps/current/decisions", "api_submit_decisions"),
}

EXPECTED_ALGO_ROUTES = {
    ("GET", "/algo/setup", "algo_setup_status"),
    ("GET", "/algo/defaults", "algo_defaults"),
    ("POST", "/algo/chat", "algo_chat"),
    ("POST", "/algo/execute", "algo_execute"),
    ("GET", "/algo/status", "algo_execution_status"),
    ("GET", "/algo/submissions", "list_submissions"),
}

EXPECTED_LEADERBOARD_ROUTES = {
    ("GET", "/v1/leaderboard", "api_get_leaderboard"),
}


def _route_triples(router):
    triples = set()
    for route in router.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in route.methods:
            if method == "HEAD":
                continue
            triples.add((method, route.path, route.name))
    return triples


# ---------------------------------------------------------------------------
# Canonical import + shim identity
# ---------------------------------------------------------------------------

def test_canonical_modules_import():
    assert agents_canon.router is not None
    assert versions_canon.router is not None
    assert agents_canon.router.__class__.__name__ == "APIRouter"


def test_shims_reexport_same_router_objects():
    assert agents_shim.router is agents_canon.router
    assert versions_shim.router is versions_canon.router
    # agent_service singleton identity preserved through both shims.
    assert agents_shim.agent_service is agents_canon.agent_service
    assert versions_shim.agent_service is versions_canon.agent_service
    assert agents_shim.agent_service is versions_shim.agent_service


def test_shared_auth_helpers_live_in_dependencies():
    # Phase 3A4: the shared owner-context/agent-access helpers moved to the
    # canonical dependencies module; the agents router imports them from there.
    assert agents_canon._owner_context is deps._owner_context
    assert agents_canon._require_agent_access is deps._require_agent_access
    assert agents_canon._require_owner_context is deps._require_owner_context


def test_protocol_auth_no_longer_imports_agents_shim():
    # protocol_auth must source the helpers from dependencies, not the old shim.
    src = Path(protocol_auth.__file__).read_text(encoding="utf-8")
    assert "from dashboard.backend.api.dependencies import" in src
    assert "from dashboard.backend.api.agents import" not in src
    # The legacy shim no longer re-exports the private helpers.
    assert not hasattr(agents_shim, "_owner_context")
    assert not hasattr(agents_shim, "_require_agent_access")


# ---------------------------------------------------------------------------
# Route identity (paths, methods, names, tags)
# ---------------------------------------------------------------------------

def test_agent_router_route_contract_unchanged():
    assert _route_triples(agents_canon.router) == EXPECTED_AGENT_ROUTES


def test_version_router_route_contract_unchanged():
    assert _route_triples(versions_canon.router) == EXPECTED_VERSION_ROUTES


def test_run_router_route_contract_unchanged():
    assert _route_triples(runs_canon.router) == EXPECTED_RUN_ROUTES


def test_environment_router_route_contract_unchanged():
    assert _route_triples(environments_canon.router) == EXPECTED_ENV_ROUTES


def test_router_prefixes_and_tags_unchanged():
    assert agents_canon.router.prefix == "/v1/agents"
    assert agents_canon.router.tags == ["agents"]
    assert versions_canon.router.prefix == "/v1"
    assert versions_canon.router.tags == ["agent-versions"]
    assert runs_canon.router.prefix == "/v1/runs"
    assert runs_canon.router.tags == ["runs"]
    assert environments_canon.router.prefix == "/v1/environments"
    assert environments_canon.router.tags == ["environments"]
    assert external_backtest_canon.router.prefix == "/v1/backtest"
    assert external_backtest_canon.router.tags == ["external-backtest"]
    assert algo_canon.router.prefix == "/algo"
    assert algo_canon.router.tags == ["algo"]
    assert leaderboard_canon.router.prefix == "/v1/leaderboard"
    assert leaderboard_canon.router.tags == ["leaderboard"]


# ---------------------------------------------------------------------------
# Run / Environment router move (Phase 3B3)
# ---------------------------------------------------------------------------

def test_run_env_canonical_modules_import():
    assert runs_canon.router.__class__.__name__ == "APIRouter"
    assert environments_canon.router.__class__.__name__ == "APIRouter"


def test_run_env_shims_reexport_same_router_objects():
    assert runs_shim.router is runs_canon.router
    assert environments_shim.router is environments_canon.router


def _all_imported_modules(path: Path):
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_canonical_run_router_imports_domain_modules():
    modules = _all_imported_modules(runs_canon.__file__)
    assert "dashboard.backend.domain.runs.service" in modules
    assert "dashboard.backend.domain.runs.repository" in modules
    assert "dashboard.backend.domain.runs.protocol" in modules
    assert "dashboard.backend.domain.runs.environment" in modules


def test_canonical_environment_router_imports_domain_module():
    modules = _all_imported_modules(environments_canon.__file__)
    assert "dashboard.backend.domain.runs.environment" in modules


# ---------------------------------------------------------------------------
# External-backtest / Algo router move (Phase 3C2)
# ---------------------------------------------------------------------------

def test_backtesting_canonical_modules_import():
    assert external_backtest_canon.router.__class__.__name__ == "APIRouter"
    assert algo_canon.router.__class__.__name__ == "APIRouter"


def test_backtesting_shims_reexport_same_router_objects():
    assert external_backtest_shim.router is external_backtest_canon.router
    assert algo_shim.router is algo_canon.router


def test_backtesting_shims_reexport_models():
    assert external_backtest_shim.StartBacktestRequest is external_backtest_canon.StartBacktestRequest
    assert external_backtest_shim.SubmitDecisionsRequest is external_backtest_canon.SubmitDecisionsRequest
    assert external_backtest_shim.TradingActionItem is external_backtest_canon.TradingActionItem
    assert algo_shim.AlgoBlocks is algo_canon.AlgoBlocks
    assert algo_shim.ChatRequest is algo_canon.ChatRequest
    assert algo_shim.ExecuteRequest is algo_canon.ExecuteRequest


def test_external_backtest_router_route_contract_unchanged():
    assert _route_triples(external_backtest_canon.router) == EXPECTED_EXTERNAL_BACKTEST_ROUTES


def test_algo_router_route_contract_unchanged():
    assert _route_triples(algo_canon.router) == EXPECTED_ALGO_ROUTES


def test_canonical_backtesting_routers_use_canonical_services():
    ext_modules = _all_imported_modules(external_backtest_canon.__file__)
    assert "dashboard.backend.domain.backtesting.external_run_service" in ext_modules
    algo_modules = _all_imported_modules(algo_canon.__file__)
    assert "dashboard.backend.domain.backtesting.algo_service" in algo_modules


# ---------------------------------------------------------------------------
# Leaderboard router move (Phase 3C4)
# ---------------------------------------------------------------------------

def test_leaderboard_canonical_module_imports():
    assert leaderboard_canon.router.__class__.__name__ == "APIRouter"


def test_leaderboard_shim_reexports_same_router_object():
    assert leaderboard_shim.router is leaderboard_canon.router


def test_leaderboard_router_route_contract_unchanged():
    assert _route_triples(leaderboard_canon.router) == EXPECTED_LEADERBOARD_ROUTES


def test_canonical_leaderboard_router_uses_canonical_service():
    modules = _all_imported_modules(leaderboard_canon.__file__)
    assert "dashboard.backend.domain.leaderboard.service" in modules


def test_each_endpoint_registered_exactly_once_in_app():
    counts = {}
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in route.methods:
            if method == "HEAD":
                continue
            counts[(method, route.path)] = counts.get((method, route.path), 0) + 1

    expected_full = set()
    all_routes = (
        EXPECTED_AGENT_ROUTES | EXPECTED_VERSION_ROUTES
        | EXPECTED_RUN_ROUTES | EXPECTED_ENV_ROUTES
        | EXPECTED_EXTERNAL_BACKTEST_ROUTES | EXPECTED_ALGO_ROUTES
        | EXPECTED_LEADERBOARD_ROUTES
    )
    for method, path, _ in all_routes:
        expected_full.add((method, f"/api{path}"))

    for key in expected_full:
        assert counts.get(key) == 1, (key, counts.get(key))


# ---------------------------------------------------------------------------
# router.py uses canonical imports
# ---------------------------------------------------------------------------

def test_router_py_uses_canonical_imports():
    src = Path(router_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert "dashboard.backend.api.routers.agents" in modules
    assert "dashboard.backend.api.routers.agent_versions" in modules
    assert "dashboard.backend.api.routers.runs" in modules
    assert "dashboard.backend.api.routers.environments" in modules
    assert "dashboard.backend.api.routers.external_backtest" in modules
    assert "dashboard.backend.api.routers.algo" in modules
    assert "dashboard.backend.api.routers.leaderboard" in modules
    # Must not import the routers from the legacy shim locations.
    assert "dashboard.backend.api.agents" not in modules
    assert "dashboard.backend.api.agent_versions" not in modules
    assert "dashboard.backend.api.runs" not in modules
    assert "dashboard.backend.api.environments" not in modules
    assert "dashboard.backend.api.external_backtest" not in modules
    assert "dashboard.backend.api.algo" not in modules
    assert "dashboard.backend.api.leaderboard" not in modules


# ---------------------------------------------------------------------------
# No circular imports
# ---------------------------------------------------------------------------

def test_no_circular_imports():
    code = (
        "import dashboard.backend.api.routers.agents\n"
        "import dashboard.backend.api.routers.agent_versions\n"
        "import dashboard.backend.api.routers.runs\n"
        "import dashboard.backend.api.routers.environments\n"
        "import dashboard.backend.api.routers.external_backtest\n"
        "import dashboard.backend.api.routers.algo\n"
        "import dashboard.backend.api.routers.leaderboard\n"
        "import dashboard.backend.api.agents\n"
        "import dashboard.backend.api.agent_versions\n"
        "import dashboard.backend.api.runs\n"
        "import dashboard.backend.api.environments\n"
        "import dashboard.backend.api.external_backtest\n"
        "import dashboard.backend.api.algo\n"
        "import dashboard.backend.api.leaderboard\n"
        "import dashboard.backend.api.router\n"
        "import dashboard.backend.api.protocol_auth\n"
        "print('ok')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout
