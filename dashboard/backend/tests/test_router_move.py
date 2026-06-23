"""Phase 3A3 — agent router move verification.

Confirms the agent HTTP routers moved to the canonical
``dashboard.backend.api.routers`` package while the old modules remain thin
re-export shims, with identical route registration and no duplicate routes.
"""

import ast
import subprocess
import sys
from pathlib import Path

from fastapi.routing import APIRoute

from dashboard.backend.api import agent_versions as versions_shim
from dashboard.backend.api import agents as agents_shim
from dashboard.backend.api import router as router_module
from dashboard.backend.api.routers import agent_versions as versions_canon
from dashboard.backend.api.routers import agents as agents_canon
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


def test_shim_reexports_private_helpers_for_protocol_auth():
    # protocol_auth lazily imports these from api.agents; they must remain.
    assert agents_shim._owner_context is agents_canon._owner_context
    assert agents_shim._require_agent_access is agents_canon._require_agent_access


# ---------------------------------------------------------------------------
# Route identity (paths, methods, names, tags)
# ---------------------------------------------------------------------------

def test_agent_router_route_contract_unchanged():
    assert _route_triples(agents_canon.router) == EXPECTED_AGENT_ROUTES


def test_version_router_route_contract_unchanged():
    assert _route_triples(versions_canon.router) == EXPECTED_VERSION_ROUTES


def test_router_prefixes_and_tags_unchanged():
    assert agents_canon.router.prefix == "/v1/agents"
    assert agents_canon.router.tags == ["agents"]
    assert versions_canon.router.prefix == "/v1"
    assert versions_canon.router.tags == ["agent-versions"]


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
    for method, path, _ in EXPECTED_AGENT_ROUTES | EXPECTED_VERSION_ROUTES:
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
    # Must not import the routers from the legacy shim locations.
    assert "dashboard.backend.api.agents" not in modules
    assert "dashboard.backend.api.agent_versions" not in modules


# ---------------------------------------------------------------------------
# No circular imports
# ---------------------------------------------------------------------------

def test_no_circular_imports():
    code = (
        "import dashboard.backend.api.routers.agents\n"
        "import dashboard.backend.api.routers.agent_versions\n"
        "import dashboard.backend.api.agents\n"
        "import dashboard.backend.api.agent_versions\n"
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
