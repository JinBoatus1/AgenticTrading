# Agent & Strategy Persistence (`DATABASE_URL` Postgres backends) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agents, agent versions, and strategies survive Render redeploys by storing them in Neon Postgres when `DATABASE_URL` is set, exactly mirroring the shipped `USERS_DATABASE_URL` users fix.

**Architecture:** Three hand-written Postgres twin classes (`PostgresAgentStore`, `PostgresAgentVersionStore`, `PostgresStrategyStore`) with public method surfaces identical to their SQLite originals, each selected by a module-level factory cloned from `users.py::_build_user_store()`. No base class, no ORM, no SQL-translation layer. Singleton names are unchanged, so zero caller changes.

**Tech Stack:** Python 3.13, FastAPI, sqlite3 (stdlib), psycopg 3 (`psycopg[binary]==3.3.4`, already a dependency), pytest.

**Spec:** `docs/superpowers/specs/2026-07-15-agent-strategy-persistence-design.md` — read it if any requirement here seems ambiguous; the spec wins.

## Global Constraints

- **Branch:** create `feat/agent-db-persistence` from current local `main` before Task 1 (`git checkout -b feat/agent-db-persistence`). NEVER push to `main` — merging `main` auto-deploys prod.
- **Dependency freeze:** `psycopg[binary]==3.3.4` is already at `requirements.txt:49`. Do NOT add any dependency.
- **Test command:** run from the repo root. `pytest` lives in `~/atl-venv`; if `pytest` is not on PATH use `~/atl-venv/bin/python -m pytest`.
- **Task 1 must land first.** It stops the test suite from ever reaching a real Postgres via an ambient `DATABASE_URL`. Do not reorder.
- **Singleton names unchanged:** `agent_store`, `agent_version_store`, `strategy_store`, `user_store` remain module-level names with the same import paths.
- **Postgres dialect conventions** (from `dashboard/backend/users_postgres.py`): per-call connections via `psycopg.connect(self.database_url, row_factory=dict_row)`; timestamps stored as `TEXT` ISO-8601 strings (the code always supplies values — never rely on DB-side defaults for timestamps); JSON stored as `TEXT` (not JSONB); SQLite `REAL` → `DOUBLE PRECISION`; `?` placeholders → `%s`.
- **Deliberate schema deviation:** `external_agents.owner_user_id` is a plain `INTEGER` with **no** FK — SQLite never enforced the declared FK (no `PRAGMA foreign_keys` anywhere), and a FK would break the split-database config (see spec).
- **Fail loud:** a set-but-unreachable `DATABASE_URL` must raise at import time (the twin's `__init__` runs `_init_schema()`). No try/except fallback to SQLite anywhere.
- **Fail visible:** every factory logs exactly one line stating the chosen backend (exact strings defined per task; tests assert on them).
- **Log the backend, never the URL:** `DATABASE_URL` contains credentials — no factory or twin may ever log it.
- **Commit style:** `feat:` / `test:` / `docs:` prefixes, short subject (repo convention).

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `dashboard/backend/tests/conftest.py` | Modify | Strip `DATABASE_URL` at import time (suite always SQLite) |
| `dashboard/backend/tests/test_env_isolation.py` | Create | Pin the import-time env stripping |
| `dashboard/backend/users.py` | Modify | Factory fallback `USERS_DATABASE_URL or DATABASE_URL` + backend log line |
| `dashboard/backend/tests/test_users_postgres.py` | Modify | Precedence + log-line dispatch tests |
| `dashboard/backend/domain/agents/repository_postgres.py` | Create | `PostgresAgentStore` (twin of `AgentStore`) |
| `dashboard/backend/domain/agents/repository.py` | Modify | `_build_agent_store()` factory + log |
| `dashboard/backend/tests/test_agent_store_postgres.py` | Create | Agent + version store dispatch tests and `@pg_only` behavioral tests |
| `dashboard/backend/domain/agents/version_repository_postgres.py` | Create | `PostgresAgentVersionStore` (twin of `AgentVersionStore`) |
| `dashboard/backend/domain/agents/version_repository.py` | Modify | `_build_agent_version_store()` factory + log |
| `dashboard/backend/domain/strategies/repository_postgres.py` | Create | `PostgresStrategyStore` (twin of `StrategyStore`, ON CONFLICT retry) |
| `dashboard/backend/domain/strategies/repository.py` | Modify | `_build_strategy_store()` factory + log |
| `dashboard/backend/tests/test_strategy_store.py` | Create | SQLite forced-collision tests (new coverage for the existing backend) |
| `dashboard/backend/tests/test_strategy_store_postgres.py` | Create | Strategy dispatch tests + `@pg_only` collision tests |
| `.env.example` | Modify | Document `DATABASE_URL` |
| `render.yaml` | Modify | `DATABASE_URL` with `sync: false` (documentation only) |
| `CLAUDE.md` | Modify | Env/credentials section + persistence gotcha |

**Import-cycle note (why the factories are safe):** each `repository_postgres.py` imports pure helpers from its SQLite sibling, and the sibling's factory imports the Postgres module *inside the factory function*, which runs at the bottom of the module — by then the helpers are already bound. This is exactly how `users.py` ↔ `users_postgres.py` already work.

**Live-Postgres testing (optional, applies to every `@pg_only` test in this plan):** without `TEST_POSTGRES_URL` those tests skip — that is the expected green state. To run them for real:

```bash
docker run --rm -d --name atl-pg-test -e POSTGRES_PASSWORD=test -e POSTGRES_DB=atl_test -p 5433:5432 postgres:16-alpine
export TEST_POSTGRES_URL=postgresql://postgres:test@localhost:5433/atl_test
# ... run pytest ...
docker stop atl-pg-test
```

---

### Task 1: Test-suite isolation — strip `DATABASE_URL` in conftest

Without this, a developer whose shell exports the prod `DATABASE_URL` would run the entire test suite against the production Neon database the moment the factories (Tasks 3–5) exist. It lands first so that can never happen, even mid-implementation.

**Files:**
- Modify: `dashboard/backend/tests/conftest.py:44-47`
- Test: `dashboard/backend/tests/test_env_isolation.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: a guarantee later tasks rely on — inside the pytest process, `DATABASE_URL` and `USERS_DATABASE_URL` are always unset except where a test monkeypatches them.

- [ ] **Step 1: Write the failing test**

Create `dashboard/backend/tests/test_env_isolation.py`:

```python
"""The suite must never see backend-selecting env vars from the developer's shell.

conftest.py strips them at import time, before any backend module is imported;
these tests pin that so a future conftest refactor can't silently drop it and
send the suite to a real Postgres.
"""

import os


def test_users_database_url_is_stripped_for_the_suite():
    assert "USERS_DATABASE_URL" not in os.environ


def test_database_url_is_stripped_for_the_suite():
    assert "DATABASE_URL" not in os.environ
```

- [ ] **Step 2: Run the test to verify it fails when the var is set**

The strip must hold even when the developer's shell exports the var, so verify red with it set:

```bash
DATABASE_URL=postgresql://fake/db pytest dashboard/backend/tests/test_env_isolation.py -v
```

Expected: `test_database_url_is_stripped_for_the_suite` FAILS (conftest doesn't strip `DATABASE_URL` yet); the `USERS_DATABASE_URL` test PASSES (already stripped).

- [ ] **Step 3: Add the strip to conftest**

In `dashboard/backend/tests/conftest.py`, immediately after the existing `os.environ.pop("USERS_DATABASE_URL", None)` line (line 47), add:

```python
# Same guarantee for DATABASE_URL: it selects Postgres backends for the
# agent / agent-version / strategy stores (and is the users-store fallback),
# so an ambient value from the developer's shell would point the whole test
# suite at a real database. Strip it before any backend module is imported.
os.environ.pop("DATABASE_URL", None)
```

Also update the module docstring's guarantee bullet (lines 23-25) to mention both vars:

```python
* An ambient ``USERS_DATABASE_URL`` or ``DATABASE_URL`` in the developer's
  shell can never make the test run reach for a real Postgres store: both are
  unset here for the same import-time reason ``DATABASE_PATH`` is pinned above.
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
DATABASE_URL=postgresql://fake/db pytest dashboard/backend/tests/test_env_isolation.py -v
```

Expected: 2 PASSED.

- [ ] **Step 5: Commit**

```bash
git add dashboard/backend/tests/conftest.py dashboard/backend/tests/test_env_isolation.py
git commit -m "test: strip DATABASE_URL from the suite environment"
```

---

### Task 2: Users factory — `DATABASE_URL` fallback + backend log line

**Files:**
- Modify: `dashboard/backend/users.py` (imports at top; `_build_user_store()` at lines 312-321)
- Test: `dashboard/backend/tests/test_users_postgres.py` (append)

**Interfaces:**
- Consumes: existing `UserStore`, `PostgresUserStore` (unchanged).
- Produces: `_build_user_store()` resolving `os.getenv("USERS_DATABASE_URL") or os.getenv("DATABASE_URL")`; log lines `"user_store backend: postgres"` / `"user_store backend: sqlite (ephemeral on Render)"`. Later tasks copy this exact factory shape.

- [ ] **Step 1: Write the failing tests**

Append to `dashboard/backend/tests/test_users_postgres.py`:

```python
def test_build_user_store_falls_back_to_database_url(monkeypatch):
    import dashboard.backend.users as users_module
    import dashboard.backend.users_postgres as users_postgres_module

    created = {}

    class FakePostgresUserStore:
        def __init__(self, database_url):
            created["database_url"] = database_url

    monkeypatch.setattr(users_postgres_module, "PostgresUserStore", FakePostgresUserStore)
    monkeypatch.delenv("USERS_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/shared")

    store = users_module._build_user_store()

    assert isinstance(store, FakePostgresUserStore)
    assert created["database_url"] == "postgresql://fake/shared"


def test_build_user_store_users_url_wins_over_database_url(monkeypatch):
    import dashboard.backend.users as users_module
    import dashboard.backend.users_postgres as users_postgres_module

    created = {}

    class FakePostgresUserStore:
        def __init__(self, database_url):
            created["database_url"] = database_url

    monkeypatch.setattr(users_postgres_module, "PostgresUserStore", FakePostgresUserStore)
    monkeypatch.setenv("USERS_DATABASE_URL", "postgresql://fake/users")
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/shared")

    store = users_module._build_user_store()

    assert created["database_url"] == "postgresql://fake/users"


def test_build_user_store_logs_sqlite_backend(monkeypatch, caplog):
    import logging

    import dashboard.backend.users as users_module

    monkeypatch.delenv("USERS_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with caplog.at_level(logging.INFO, logger="dashboard.backend.users"):
        store = users_module._build_user_store()
    assert isinstance(store, users_module.UserStore)
    assert "user_store backend: sqlite (ephemeral on Render)" in caplog.text
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest dashboard/backend/tests/test_users_postgres.py -v
```

Expected: the 3 new tests FAIL (`test_build_user_store_falls_back_to_database_url` gets a `UserStore`, the precedence test never constructs the fake, the log test finds no log line). The 2 pre-existing dispatch tests still PASS; `@pg_only` tests skip.

- [ ] **Step 3: Implement**

In `dashboard/backend/users.py`, add `import logging` to the stdlib import block at the top (alphabetical — between `import hashlib` and `import os`), and add a module logger right after the imports, before `SESSION_TTL_DAYS`:

```python
logger = logging.getLogger(__name__)
```

Replace `_build_user_store()` (lines 312-318) with:

```python
def _build_user_store():
    database_url = os.getenv("USERS_DATABASE_URL") or os.getenv("DATABASE_URL")
    if database_url:
        from dashboard.backend.users_postgres import PostgresUserStore

        logger.info("user_store backend: postgres")
        return PostgresUserStore(database_url)
    logger.info("user_store backend: sqlite (ephemeral on Render)")
    return UserStore()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest dashboard/backend/tests/test_users_postgres.py dashboard/backend/tests/test_auth.py -v
```

Expected: all PASS (plus `@pg_only` skips). `test_auth.py` exercises the SQLite `UserStore` through the auth routes, proving the factory change didn't disturb the default path.

- [ ] **Step 5: Commit**

```bash
git add dashboard/backend/users.py dashboard/backend/tests/test_users_postgres.py
git commit -m "feat: users store falls back to DATABASE_URL, logs backend choice"
```

---

### Task 3: `PostgresAgentStore` + agent-store factory

The heart of the change: the twin of `AgentStore` (14 public methods) and the factory that selects it. `resolve_api_key()` is the sole auth path for `/api/v1` and `/api/v2` — port with care.

**Files:**
- Create: `dashboard/backend/domain/agents/repository_postgres.py`
- Modify: `dashboard/backend/domain/agents/repository.py` (imports; replace line 551 `agent_store = AgentStore()`)
- Test: `dashboard/backend/tests/test_agent_store_postgres.py` (create)

**Interfaces:**
- Consumes: pure helpers from the SQLite module — `DEFAULT_SCOPES`, `_UNSET`, `_utcnow_iso()`, `_hash_api_key(api_key: str) -> str`, `_new_api_key() -> str`, `_public_agent(row) -> Dict[str, Any]` (all defined at `repository.py:22-71`, before the factory runs — no import cycle).
- Produces: `PostgresAgentStore(database_url: str)` with methods signature-identical to `AgentStore`: `create_agent`, `register_or_get_agent`, `list_agents`, `list_builtin_agents`, `get_agent`, `get_agent_by_session`, `resolve_api_key`, `claim_browser_agents_to_user`, `claim_agent`, `reclaim_agent`, `rotate_api_key`, `update_agent`, `delete_agent`, `owns_agent`; plus `_get_connection()` (test fixtures call it). Factory `_build_agent_store()`; log lines `"agent_store backend: postgres"` / `"agent_store backend: sqlite (ephemeral on Render)"`.

- [ ] **Step 1: Write the failing tests**

Create `dashboard/backend/tests/test_agent_store_postgres.py`:

```python
"""PostgresAgentStore / PostgresAgentVersionStore tests.

Two tiers, mirroring test_users_postgres.py:
1. Dispatch-logic tests (no live Postgres needed) - verify the module
   factories pick the right store class based on DATABASE_URL.
2. Behavioral tests against a real Postgres - skipped unless
   TEST_POSTGRES_URL is set. Point it at a throwaway database, e.g.:
     docker run --rm -e POSTGRES_PASSWORD=test -e POSTGRES_DB=atl_test \
       -p 5433:5432 postgres:16-alpine
     export TEST_POSTGRES_URL=postgresql://postgres:test@localhost:5433/atl_test

Do NOT copy the raw-SQL fixture pattern from test_v2_http_runs.py /
test_v2_auth.py (SQLite-only `?` placeholders); use public store methods.
"""

import logging
import os

import pytest

TEST_POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")

pg_only = pytest.mark.skipif(
    not TEST_POSTGRES_URL,
    reason="TEST_POSTGRES_URL not set; skipping live-Postgres tests",
)


# --- dispatch tests (agent store) -------------------------------------------

def test_build_agent_store_defaults_to_sqlite(monkeypatch, caplog):
    import dashboard.backend.domain.agents.repository as repo_module

    monkeypatch.delenv("DATABASE_URL", raising=False)
    with caplog.at_level(logging.INFO, logger="dashboard.backend.domain.agents.repository"):
        store = repo_module._build_agent_store()
    assert isinstance(store, repo_module.AgentStore)
    assert "agent_store backend: sqlite (ephemeral on Render)" in caplog.text


def test_build_agent_store_picks_postgres_when_url_set(monkeypatch, caplog):
    import dashboard.backend.domain.agents.repository as repo_module
    import dashboard.backend.domain.agents.repository_postgres as repo_pg_module

    created = {}

    class FakePostgresAgentStore:
        def __init__(self, database_url):
            created["database_url"] = database_url

    monkeypatch.setattr(repo_pg_module, "PostgresAgentStore", FakePostgresAgentStore)
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/db")

    with caplog.at_level(logging.INFO, logger="dashboard.backend.domain.agents.repository"):
        store = repo_module._build_agent_store()

    assert isinstance(store, FakePostgresAgentStore)
    assert created["database_url"] == "postgresql://fake/db"
    assert "agent_store backend: postgres" in caplog.text


# --- live-Postgres behavioral tests (agent store) ---------------------------

@pytest.fixture
def pg_agent_store():
    from dashboard.backend.domain.agents.repository_postgres import PostgresAgentStore

    store = PostgresAgentStore(TEST_POSTGRES_URL)
    with store._get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM external_agents")
    yield store


@pg_only
def test_agent_key_lifecycle_postgres(pg_agent_store):
    created = pg_agent_store.create_agent(
        name="PG Agent", owner_browser_session="bs_1", description="hello"
    )
    assert created["agent_id"].startswith("agent_")
    assert created["api_key"].startswith("ag_")
    assert created["api_key_prefix"] == created["api_key"][:12]

    resolved = pg_agent_store.resolve_api_key(created["api_key"])
    assert resolved is not None
    assert resolved["agent_id"] == created["agent_id"]
    assert resolved["last_used_at"] is not None

    new_key = pg_agent_store.rotate_api_key(created["agent_id"])
    assert new_key is not None and new_key != created["api_key"]
    assert pg_agent_store.resolve_api_key(created["api_key"]) is None
    assert pg_agent_store.resolve_api_key(new_key)["agent_id"] == created["agent_id"]

    assert pg_agent_store.rotate_api_key("agent_missing") is None
    assert pg_agent_store.resolve_api_key("") is None


@pg_only
def test_browser_claim_and_ownership_postgres(pg_agent_store):
    created = pg_agent_store.create_agent(name="Claimable", owner_browser_session="bs_2")
    assert pg_agent_store.owns_agent(created, owner_browser_session="bs_2") is True
    assert pg_agent_store.owns_agent(created, owner_user_id=42) is False

    claimed = pg_agent_store.claim_browser_agents_to_user("bs_2", user_id=42)
    assert claimed == 1
    assert pg_agent_store.owns_agent(created, owner_user_id=42) is True

    listed = pg_agent_store.list_agents(owner_user_id=42)
    assert [a["agent_id"] for a in listed] == [created["agent_id"]]
    assert listed[0]["owner_user_id"] == 42


@pg_only
def test_register_or_get_agent_is_idempotent_postgres(pg_agent_store):
    first = pg_agent_store.register_or_get_agent(session_id="sess-1", name="A")
    again = pg_agent_store.register_or_get_agent(session_id="sess-1", name="A renamed")
    assert again["agent_id"] == first["agent_id"]
    assert again["name"] == "A renamed"
    assert pg_agent_store.get_agent_by_session("sess-1")["agent_id"] == first["agent_id"]


@pg_only
def test_update_agent_partial_updates_postgres(pg_agent_store):
    created = pg_agent_store.create_agent(name="Updatable")

    updated = pg_agent_store.update_agent(
        created["agent_id"], name="Renamed", pipeline=[{"presetKey": "news"}]
    )
    assert updated["name"] == "Renamed"
    assert updated["pipeline"] == [{"presetKey": "news"}]

    # Omitted kwargs (the _UNSET sentinel) must leave stored fields untouched.
    updated2 = pg_agent_store.update_agent(created["agent_id"], description="desc only")
    assert updated2["description"] == "desc only"
    assert updated2["pipeline"] == [{"presetKey": "news"}]

    # Explicit None clears the pipeline.
    updated3 = pg_agent_store.update_agent(created["agent_id"], pipeline=None)
    assert updated3["pipeline"] is None

    # No kwargs at all returns the current record unchanged.
    same = pg_agent_store.update_agent(created["agent_id"])
    assert same["name"] == "Renamed"

    assert pg_agent_store.update_agent("agent_missing", name="X") is None


@pg_only
def test_builtin_listing_and_delete_postgres(pg_agent_store):
    builtin = pg_agent_store.create_agent(name="Builtin", agent_type="builtin")
    external = pg_agent_store.create_agent(name="External")

    builtin_ids = [a["agent_id"] for a in pg_agent_store.list_builtin_agents()]
    assert builtin["agent_id"] in builtin_ids
    assert external["agent_id"] not in builtin_ids

    assert pg_agent_store.delete_agent(builtin["agent_id"]) is True
    assert pg_agent_store.delete_agent(builtin["agent_id"]) is False
    assert pg_agent_store.get_agent(builtin["agent_id"]) is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest dashboard/backend/tests/test_agent_store_postgres.py -v
```

Expected: the two dispatch tests FAIL — `test_build_agent_store_defaults_to_sqlite` with `AttributeError: module ... has no attribute '_build_agent_store'`, the other with `ModuleNotFoundError` for `repository_postgres`. `@pg_only` tests skip (or ERROR on missing module if `TEST_POSTGRES_URL` is set — either is an acceptable red).

- [ ] **Step 3: Create `dashboard/backend/domain/agents/repository_postgres.py`**

```python
"""Postgres-backed AgentStore implementation.

Selected instead of the default SQLite AgentStore when DATABASE_URL is set
(see repository.py's _build_agent_store). Exists because the SQLite store
lives in DATABASE_PATH, which resets to the committed seed database on every
deploy of the disk-less Render free-tier host -- silently deleting every
registered agent and invalidating every issued API key (resolve_api_key is
the sole auth path for /api/v1 and /api/v2). Method surface, return schemas,
and behavior are identical to AgentStore; only the SQL dialect differs.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional

import psycopg
from psycopg.rows import dict_row

from dashboard.backend.domain.agents.repository import (
    DEFAULT_SCOPES,
    _UNSET,
    _hash_api_key,
    _new_api_key,
    _public_agent,
    _utcnow_iso,
)


class PostgresAgentStore:
    """Persist external agents and their trading session IDs, backed by Postgres."""

    def __init__(self, database_url: str):
        self.database_url = database_url
        self._init_schema()

    def _get_connection(self) -> psycopg.Connection:
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def _init_schema(self) -> None:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                # owner_user_id is deliberately a plain INTEGER with no FK to
                # users(id): SQLite never enforced the declared FK (no PRAGMA
                # foreign_keys anywhere), the app owns this integrity
                # (owns_agent / claim_browser_agents_to_user), and a FK would
                # break the split config where USERS_DATABASE_URL points at a
                # different database (Postgres has no cross-database FKs).
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS external_agents (
                        agent_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        session_id TEXT NOT NULL UNIQUE,
                        api_key_hash TEXT NOT NULL UNIQUE,
                        api_key_prefix TEXT NOT NULL,
                        model_name TEXT NOT NULL DEFAULT 'local-model',
                        scopes TEXT NOT NULL DEFAULT '{DEFAULT_SCOPES}',
                        owner_user_id INTEGER,
                        owner_browser_session TEXT,
                        created_at TEXT,
                        last_used_at TEXT,
                        agent_type TEXT NOT NULL DEFAULT 'external',
                        description TEXT,
                        pipeline_config TEXT,
                        cash_allocation DOUBLE PRECISION
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_external_agents_owner_user
                    ON external_agents(owner_user_id)
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_external_agents_owner_browser
                    ON external_agents(owner_browser_session)
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_external_agents_type
                    ON external_agents(agent_type)
                    """
                )

    def create_agent(
        self,
        *,
        name: str,
        model_name: str = "local-model",
        owner_user_id: Optional[int] = None,
        owner_browser_session: Optional[str] = None,
        session_id: Optional[str] = None,
        agent_type: str = "external",
        description: Optional[str] = None,
        cash_allocation: Optional[float] = None,
    ) -> Dict[str, Any]:
        agent_id = f"agent_{uuid.uuid4().hex[:12]}"
        session_id = session_id or str(uuid.uuid4())
        api_key = _new_api_key()
        api_key_hash = _hash_api_key(api_key)
        api_key_prefix = api_key[:12]
        now = _utcnow_iso()

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO external_agents (
                        agent_id, name, session_id, api_key_hash, api_key_prefix,
                        model_name, agent_type, description, cash_allocation,
                        owner_user_id, owner_browser_session, created_at, last_used_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING *
                    """,
                    (
                        agent_id,
                        name.strip(),
                        session_id,
                        api_key_hash,
                        api_key_prefix,
                        model_name.strip() or "local-model",
                        (agent_type or "external").strip() or "external",
                        (description or None),
                        cash_allocation,
                        owner_user_id,
                        owner_browser_session,
                        now,
                        now,
                    ),
                )
                row = cur.fetchone()

        agent = _public_agent(row)
        agent["api_key"] = api_key
        return agent

    def register_or_get_agent(
        self,
        *,
        session_id: str,
        name: str,
        model_name: str = "local-model",
        owner_user_id: Optional[int] = None,
        owner_browser_session: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Link an existing trading session to an agent (idempotent)."""
        existing = self.get_agent_by_session(session_id)
        if existing:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE external_agents
                        SET name = %s, model_name = %s, last_used_at = %s,
                            owner_user_id = COALESCE(%s, owner_user_id),
                            owner_browser_session = COALESCE(%s, owner_browser_session)
                        WHERE session_id = %s
                        """,
                        (
                            name.strip(),
                            model_name.strip() or "local-model",
                            _utcnow_iso(),
                            owner_user_id,
                            owner_browser_session,
                            session_id,
                        ),
                    )
            return self.get_agent_by_session(session_id) or existing

        return self.create_agent(
            name=name,
            model_name=model_name,
            owner_user_id=owner_user_id,
            owner_browser_session=owner_browser_session,
            session_id=session_id,
        )

    def list_agents(
        self,
        *,
        owner_user_id: Optional[int] = None,
        owner_browser_session: Optional[str] = None,
        trading_session_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        seen: set = set()

        with self._get_connection() as conn:
            with conn.cursor() as cur:

                def _add_rows(query: str, params: tuple) -> None:
                    cur.execute(query, params)
                    for row in cur.fetchall():
                        if row["agent_id"] not in seen:
                            seen.add(row["agent_id"])
                            rows.append(row)

                if owner_user_id is not None:
                    _add_rows(
                        """
                        SELECT * FROM external_agents
                        WHERE owner_user_id = %s
                        ORDER BY created_at DESC
                        """,
                        (owner_user_id,),
                    )
                elif owner_browser_session:
                    _add_rows(
                        """
                        SELECT * FROM external_agents
                        WHERE owner_browser_session = %s
                        ORDER BY created_at DESC
                        """,
                        (owner_browser_session,),
                    )

                if trading_session_id:
                    _add_rows(
                        """
                        SELECT * FROM external_agents
                        WHERE session_id = %s
                        ORDER BY created_at DESC
                        """,
                        (trading_session_id,),
                    )

        return [_public_agent(row) for row in rows]

    def list_builtin_agents(self) -> List[Dict[str, Any]]:
        """List every built-in (platform-hosted) agent, newest first.

        Built-in agents are globally discoverable (e.g. from the Discord
        ``/agent`` command) regardless of which account created them.
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM external_agents
                    WHERE agent_type = 'builtin'
                    ORDER BY created_at DESC
                    """
                )
                rows = cur.fetchall()
        return [_public_agent(row) for row in rows]

    def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM external_agents WHERE agent_id = %s", (agent_id,)
                )
                row = cur.fetchone()
        return _public_agent(row) if row else None

    def get_agent_by_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM external_agents WHERE session_id = %s", (session_id,)
                )
                row = cur.fetchone()
        return _public_agent(row) if row else None

    def resolve_api_key(self, api_key: str) -> Optional[Dict[str, Any]]:
        if not api_key or not api_key.strip():
            return None
        key_hash = _hash_api_key(api_key.strip())
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM external_agents WHERE api_key_hash = %s",
                    (key_hash,),
                )
                row = cur.fetchone()
                if row:
                    cur.execute(
                        "UPDATE external_agents SET last_used_at = %s WHERE agent_id = %s",
                        (_utcnow_iso(), row["agent_id"]),
                    )
        return _public_agent(row) if row else None

    def claim_browser_agents_to_user(
        self,
        browser_session: str,
        user_id: int,
    ) -> int:
        """Attach all browser-owned agents to a logged-in user account."""
        if not browser_session or user_id is None:
            return 0
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE external_agents
                    SET owner_user_id = %s,
                        owner_browser_session = COALESCE(owner_browser_session, %s),
                        last_used_at = %s
                    WHERE owner_browser_session = %s
                      AND (owner_user_id IS NULL OR owner_user_id = %s)
                    """,
                    (user_id, browser_session, _utcnow_iso(), browser_session, user_id),
                )
                updated = cur.rowcount
        return updated

    def claim_agent(
        self,
        agent_id: str,
        *,
        owner_user_id: Optional[int] = None,
        owner_browser_session: Optional[str] = None,
    ) -> None:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE external_agents
                    SET owner_user_id = COALESCE(%s, owner_user_id),
                        owner_browser_session = COALESCE(%s, owner_browser_session),
                        last_used_at = %s
                    WHERE agent_id = %s
                    """,
                    (owner_user_id, owner_browser_session, _utcnow_iso(), agent_id),
                )

    def reclaim_agent(
        self,
        agent_id: str,
        *,
        owner_user_id: Optional[int] = None,
        owner_browser_session: Optional[str] = None,
    ) -> None:
        """Re-bind an agent to the current browser/user (dashboard session proof)."""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE external_agents
                    SET owner_user_id = COALESCE(%s, owner_user_id),
                        owner_browser_session = %s,
                        last_used_at = %s
                    WHERE agent_id = %s
                    """,
                    (owner_user_id, owner_browser_session, _utcnow_iso(), agent_id),
                )

    def rotate_api_key(self, agent_id: str) -> Optional[str]:
        """Issue a new API key for an agent. Returns the raw key once."""
        api_key = _new_api_key()
        api_key_hash = _hash_api_key(api_key)
        api_key_prefix = api_key[:12]
        now = _utcnow_iso()

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE external_agents
                    SET api_key_hash = %s,
                        api_key_prefix = %s,
                        last_used_at = %s
                    WHERE agent_id = %s
                    """,
                    (api_key_hash, api_key_prefix, now, agent_id),
                )
                updated = cur.rowcount > 0
        return api_key if updated else None

    def update_agent(
        self,
        agent_id: str,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        pipeline: Any = _UNSET,
        cash_allocation: Any = _UNSET,
    ) -> Optional[Dict[str, Any]]:
        """Update display fields for an agent. Returns the updated record or None.

        ``pipeline`` uses a sentinel default so callers can distinguish "leave
        the stored pipeline untouched" (omit the arg) from "clear it" (pass
        ``None``). A list is serialized to JSON.
        """
        sets: list[str] = []
        params: list[Any] = []
        if name is not None:
            sets.append("name = %s")
            params.append(name.strip())
        if description is not None:
            sets.append("description = %s")
            params.append(description.strip() if description else None)
        if pipeline is not _UNSET:
            sets.append("pipeline_config = %s")
            params.append(json.dumps(pipeline) if pipeline else None)
        if cash_allocation is not _UNSET:
            sets.append("cash_allocation = %s")
            params.append(cash_allocation)
        if not sets:
            return self.get_agent(agent_id)
        sets.append("last_used_at = %s")
        params.append(_utcnow_iso())
        params.append(agent_id)
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE external_agents SET {', '.join(sets)} "
                    "WHERE agent_id = %s RETURNING *",
                    params,
                )
                row = cur.fetchone()
        return _public_agent(row) if row else None

    def delete_agent(self, agent_id: str) -> bool:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM external_agents WHERE agent_id = %s", (agent_id,)
                )
                deleted = cur.rowcount > 0
        return deleted

    def owns_agent(
        self,
        agent: Dict[str, Any],
        *,
        owner_user_id: Optional[int] = None,
        owner_browser_session: Optional[str] = None,
    ) -> bool:
        agent_id = agent.get("agent_id") if isinstance(agent, dict) else agent
        if not agent_id:
            return False
        # Read the ownership columns straight from the row. owner_browser_session
        # is deliberately omitted from the public agent dict (it is a private
        # credential), so we must NOT rely on the passed-in dict for it — doing so
        # is why owner_browser_session ownership silently never matched.
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT owner_user_id, owner_browser_session "
                    "FROM external_agents WHERE agent_id = %s",
                    (agent_id,),
                )
                row = cur.fetchone()
        if not row:
            return False
        if owner_user_id is not None and row["owner_user_id"] == owner_user_id:
            return True
        if owner_browser_session and row["owner_browser_session"] == owner_browser_session:
            return True
        # NOTE: session_id is NOT an ownership credential. It is an internal
        # trading-session identifier that is discoverable (it used to be returned
        # by the public /builtin listing), so matching it against a caller-supplied
        # session would let anyone who learned it take over the agent. Ownership
        # requires owner_user_id or owner_browser_session (a real, private
        # credential), or the agent API key (checked at the route layer).
        return False
```

- [ ] **Step 4: Add the factory to `dashboard/backend/domain/agents/repository.py`**

Add `import logging` and `import os` to the stdlib import block at the top (alphabetical order within the block), and a module logger after the imports (before `DEFAULT_SCOPES`):

```python
logger = logging.getLogger(__name__)
```

Replace the final line (`agent_store = AgentStore()`, line 551) with:

```python
def _build_agent_store():
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        from dashboard.backend.domain.agents.repository_postgres import PostgresAgentStore

        logger.info("agent_store backend: postgres")
        return PostgresAgentStore(database_url)
    logger.info("agent_store backend: sqlite (ephemeral on Render)")
    return AgentStore()


agent_store = _build_agent_store()
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest dashboard/backend/tests/test_agent_store_postgres.py -v
```

Expected: 2 dispatch tests PASS, 5 `@pg_only` tests skip (or PASS with `TEST_POSTGRES_URL` set — see the docker recipe in the header).

- [ ] **Step 6: Run the whole suite (the factory touched a module every agent route imports)**

```bash
pytest dashboard/backend/tests/ -q
```

Expected: green (same skip count as before this task, +5 new skips without `TEST_POSTGRES_URL`). Note: if `test_deleted_shim_is_not_importable` fails with `DID NOT RAISE`, that's stale pre-refactor bytecode, not this change — `rm -rf dashboard/backend/engines dashboard/backend/services` and re-run (see CLAUDE.md gotchas).

- [ ] **Step 7: Commit**

```bash
git add dashboard/backend/domain/agents/repository_postgres.py dashboard/backend/domain/agents/repository.py dashboard/backend/tests/test_agent_store_postgres.py
git commit -m "feat: Postgres agent store behind DATABASE_URL"
```

---

### Task 4: `PostgresAgentVersionStore` + version-store factory

**Files:**
- Create: `dashboard/backend/domain/agents/version_repository_postgres.py`
- Modify: `dashboard/backend/domain/agents/version_repository.py` (imports; replace line 198 `agent_version_store = AgentVersionStore()`)
- Test: `dashboard/backend/tests/test_agent_store_postgres.py` (append)

**Interfaces:**
- Consumes: pure helpers from `version_repository.py` — `_utcnow_iso()`, `_new_version_id()`, `_short_hash(value) -> Optional[str]`, `_public_version(row) -> Dict[str, Any]` (defined at `version_repository.py:30-67`, before the factory runs). NOTE: this module's `_utcnow_iso` is its own copy — import from `version_repository`, not from `repository`.
- Produces: `PostgresAgentVersionStore(database_url: str)` with `create_version`, `get_version`, `list_versions` signature-identical to `AgentVersionStore`, plus `_get_connection()`. Factory `_build_agent_version_store()`; log lines `"agent_version_store backend: postgres"` / `"agent_version_store backend: sqlite (ephemeral on Render)"`.

- [ ] **Step 1: Write the failing tests**

Append to `dashboard/backend/tests/test_agent_store_postgres.py`:

```python
# --- dispatch tests (agent version store) ------------------------------------

def test_build_agent_version_store_defaults_to_sqlite(monkeypatch, caplog):
    import dashboard.backend.domain.agents.version_repository as vrepo_module

    monkeypatch.delenv("DATABASE_URL", raising=False)
    with caplog.at_level(
        logging.INFO, logger="dashboard.backend.domain.agents.version_repository"
    ):
        store = vrepo_module._build_agent_version_store()
    assert isinstance(store, vrepo_module.AgentVersionStore)
    assert "agent_version_store backend: sqlite (ephemeral on Render)" in caplog.text


def test_build_agent_version_store_picks_postgres_when_url_set(monkeypatch):
    import dashboard.backend.domain.agents.version_repository as vrepo_module
    import dashboard.backend.domain.agents.version_repository_postgres as vrepo_pg_module

    created = {}

    class FakePostgresAgentVersionStore:
        def __init__(self, database_url):
            created["database_url"] = database_url

    monkeypatch.setattr(
        vrepo_pg_module, "PostgresAgentVersionStore", FakePostgresAgentVersionStore
    )
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/db")

    store = vrepo_module._build_agent_version_store()

    assert isinstance(store, FakePostgresAgentVersionStore)
    assert created["database_url"] == "postgresql://fake/db"


# --- live-Postgres behavioral tests (agent version store) --------------------

@pytest.fixture
def pg_version_store():
    from dashboard.backend.domain.agents.version_repository_postgres import (
        PostgresAgentVersionStore,
    )

    store = PostgresAgentVersionStore(TEST_POSTGRES_URL)
    with store._get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM agent_versions")
    yield store


@pg_only
def test_version_create_get_list_postgres(pg_version_store):
    v1 = pg_version_store.create_version(
        agent_id="agent_x",
        version="1.0",
        model_backbones=["claude-sonnet-5"],
        prompt="You are a trader.",
        config={"risk": "low"},
    )
    assert v1["agent_version_id"].startswith("agv_")
    assert v1["model_backbones"] == ["claude-sonnet-5"]
    # Hashes derived from raw prompt/config when not passed explicitly.
    assert v1["prompt_hash"] and len(v1["prompt_hash"]) == 16
    assert v1["config_hash"] and len(v1["config_hash"]) == 16

    v2 = pg_version_store.create_version(agent_id="agent_x", version="1.1")
    listed = pg_version_store.list_versions("agent_x")
    # Both creates can land in the same second (1s timestamp resolution), and
    # the tiebreak is agent_version_id DESC (random hex) — so assert membership
    # and count, not a specific order.
    assert {v["agent_version_id"] for v in listed} == {
        v1["agent_version_id"],
        v2["agent_version_id"],
    }
    assert len(listed) == 2

    fetched = pg_version_store.get_version(v1["agent_version_id"])
    assert fetched == v1
    assert pg_version_store.get_version("agv_missing") is None
    assert pg_version_store.list_versions("agent_other") == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest dashboard/backend/tests/test_agent_store_postgres.py -v
```

Expected: `test_build_agent_version_store_defaults_to_sqlite` FAILS with `AttributeError` (no `_build_agent_version_store`); the picks-postgres test FAILS with `ModuleNotFoundError`. Task 3's tests still PASS.

- [ ] **Step 3: Create `dashboard/backend/domain/agents/version_repository_postgres.py`**

```python
"""Postgres-backed AgentVersionStore implementation.

Selected instead of the default SQLite AgentVersionStore when DATABASE_URL is
set (see version_repository.py's _build_agent_version_store). Versions are
immutable reproducibility snapshots and were previously lost with their agents
on every deploy of the disk-less Render free-tier host. Method surface, return
schemas, and behavior are identical to AgentVersionStore; only the SQL dialect
differs.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import psycopg
from psycopg.rows import dict_row

from dashboard.backend.domain.agents.version_repository import (
    _new_version_id,
    _public_version,
    _short_hash,
    _utcnow_iso,
)


class PostgresAgentVersionStore:
    """Persist immutable agent version snapshots, backed by Postgres."""

    def __init__(self, database_url: str):
        self.database_url = database_url
        self._init_schema()

    def _get_connection(self) -> psycopg.Connection:
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def _init_schema(self) -> None:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS agent_versions (
                        agent_version_id TEXT PRIMARY KEY,
                        agent_id TEXT NOT NULL,
                        version TEXT NOT NULL,
                        execution_mode TEXT NOT NULL DEFAULT 'external',
                        architecture TEXT,
                        model_backbones TEXT NOT NULL DEFAULT '[]',
                        decision_frequency TEXT NOT NULL DEFAULT '1h',
                        code_commit TEXT,
                        prompt_hash TEXT,
                        config_hash TEXT,
                        verification_level TEXT NOT NULL DEFAULT 'self_reported',
                        created_at TEXT
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_agent_versions_agent
                    ON agent_versions(agent_id, created_at)
                    """
                )

    def create_version(
        self,
        *,
        agent_id: str,
        version: str,
        execution_mode: str = "external",
        architecture: Optional[str] = None,
        model_backbones: Optional[List[str]] = None,
        decision_frequency: str = "1h",
        code_commit: Optional[str] = None,
        prompt_hash: Optional[str] = None,
        config_hash: Optional[str] = None,
        prompt: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        verification_level: str = "self_reported",
    ) -> Dict[str, Any]:
        """Create a new immutable version. Hashes can be derived from raw
        prompt/config if explicit hashes are not provided."""
        agent_version_id = _new_version_id()
        now = _utcnow_iso()
        backbones = json.dumps(list(model_backbones or []))
        prompt_hash = prompt_hash or _short_hash(prompt)
        config_hash = config_hash or _short_hash(config)

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO agent_versions (
                        agent_version_id, agent_id, version, execution_mode, architecture,
                        model_backbones, decision_frequency, code_commit, prompt_hash,
                        config_hash, verification_level, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING *
                    """,
                    (
                        agent_version_id,
                        agent_id,
                        version,
                        execution_mode,
                        architecture,
                        backbones,
                        decision_frequency,
                        code_commit,
                        prompt_hash,
                        config_hash,
                        verification_level,
                        now,
                    ),
                )
                row = cur.fetchone()
        return _public_version(row)

    def get_version(self, agent_version_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM agent_versions WHERE agent_version_id = %s",
                    (agent_version_id,),
                )
                row = cur.fetchone()
        return _public_version(row) if row else None

    def list_versions(self, agent_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM agent_versions
                    WHERE agent_id = %s
                    ORDER BY created_at DESC, agent_version_id DESC
                    """,
                    (agent_id,),
                )
                rows = cur.fetchall()
        return [_public_version(row) for row in rows]
```

- [ ] **Step 4: Add the factory to `dashboard/backend/domain/agents/version_repository.py`**

Add `import logging` and `import os` to the stdlib import block at the top, and a module logger after the imports (before `VALID_EXECUTION_MODES`):

```python
logger = logging.getLogger(__name__)
```

Replace the final line (`agent_version_store = AgentVersionStore()`, line 198) with:

```python
def _build_agent_version_store():
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        from dashboard.backend.domain.agents.version_repository_postgres import (
            PostgresAgentVersionStore,
        )

        logger.info("agent_version_store backend: postgres")
        return PostgresAgentVersionStore(database_url)
    logger.info("agent_version_store backend: sqlite (ephemeral on Render)")
    return AgentVersionStore()


agent_version_store = _build_agent_version_store()
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest dashboard/backend/tests/test_agent_store_postgres.py -v
```

Expected: all dispatch tests PASS; `@pg_only` skip (or PASS with live Postgres).

- [ ] **Step 6: Commit**

```bash
git add dashboard/backend/domain/agents/version_repository_postgres.py dashboard/backend/domain/agents/version_repository.py dashboard/backend/tests/test_agent_store_postgres.py
git commit -m "feat: Postgres agent version store behind DATABASE_URL"
```

---

### Task 5: `PostgresStrategyStore` (restructured share-code retry) + strategy factory + collision tests

The one non-mechanical port. `StrategyStore.create()` (`domain/strategies/repository.py:95-128`) catches `sqlite3.IntegrityError` per attempt and retries **on the same connection**. In Postgres the first `UniqueViolation` aborts the transaction and every later statement on that connection raises `InFailedSqlTransaction` — a literal port 500s on the first real collision. The Postgres twin instead uses `INSERT ... ON CONFLICT (code) DO NOTHING` and treats `cursor.rowcount == 0` as the collision signal. Retry count (20), the widened 16-char fallback, and the final `RuntimeError` are preserved exactly.

No existing test forces a collision on *either* backend, so this task also adds SQLite collision tests (new coverage, runs everywhere).

**Files:**
- Create: `dashboard/backend/domain/strategies/repository_postgres.py`
- Modify: `dashboard/backend/domain/strategies/repository.py` (imports; replace line 156 `strategy_store = StrategyStore()`)
- Test: `dashboard/backend/tests/test_strategy_store.py` (create — SQLite collision tests)
- Test: `dashboard/backend/tests/test_strategy_store_postgres.py` (create — dispatch + `@pg_only`)

**Interfaces:**
- Consumes: from `domain/strategies/repository.py` — `_CODE_LENGTH` (int, = 8), `_now_iso()` (NOTE: this module's timestamp helper keeps microseconds and is named `_now_iso`, unlike the agent modules' `_utcnow_iso`), `_public(row) -> dict`.
- Produces: `PostgresStrategyStore(database_url: str)` with `create`, `get`, `set_last_run` signature-identical to `StrategyStore`, plus `_get_connection()`. Factory `_build_strategy_store()`; log lines `"strategy_store backend: postgres"` / `"strategy_store backend: sqlite (ephemeral on Render)"`. The module-level wrappers `create_strategy`/`get_strategy`/`set_last_run` keep delegating to the `strategy_store` singleton unchanged.

- [ ] **Step 1: Write the failing SQLite collision tests**

Create `dashboard/backend/tests/test_strategy_store.py`:

```python
"""StrategyStore share-code collision behavior (SQLite backend).

create() retries up to 20 times on a code collision, then widens the code
space (16 hex chars) and tries once more before raising. No prior test forced
a real collision (random 8-hex codes essentially never collide by chance), so
this pins the retry loop for the first time. The Postgres twin has the same
tests in test_strategy_store_postgres.py -- its retry loop is structurally
different (ON CONFLICT DO NOTHING instead of catching IntegrityError) and must
behave identically.
"""

import pytest

import dashboard.backend.domain.strategies.repository as strategies_module


@pytest.fixture
def sqlite_store(tmp_path):
    return strategies_module.StrategyStore(tmp_path / "strategies_test.db")


def test_create_retries_past_a_code_collision(sqlite_store, monkeypatch):
    first = sqlite_store.create(prompt="first strategy")

    codes = iter([first["code"], "fresh456"])
    monkeypatch.setattr(
        strategies_module.secrets, "token_hex", lambda nbytes: next(codes)
    )

    second = sqlite_store.create(prompt="second strategy")
    assert second["code"] == "fresh456"
    assert sqlite_store.get(first["code"])["prompt"] == "first strategy"
    assert sqlite_store.get("fresh456")["prompt"] == "second strategy"


def test_create_widens_code_space_after_20_collisions(sqlite_store, monkeypatch):
    first = sqlite_store.create(prompt="first strategy")

    calls = {"n": 0}

    def fake_token_hex(nbytes):
        calls["n"] += 1
        if calls["n"] <= 20:
            return first["code"]  # narrow attempts all collide
        return "w" * 16  # widened attempt succeeds

    monkeypatch.setattr(strategies_module.secrets, "token_hex", fake_token_hex)

    second = sqlite_store.create(prompt="second strategy")
    assert second["code"] == "w" * 16
    assert calls["n"] == 21


def test_create_raises_when_even_widened_code_collides(sqlite_store, monkeypatch):
    first = sqlite_store.create(prompt="first strategy")

    monkeypatch.setattr(
        strategies_module.secrets, "token_hex", lambda nbytes: first["code"]
    )

    with pytest.raises(RuntimeError):
        sqlite_store.create(prompt="second strategy")
```

- [ ] **Step 2: Run the SQLite collision tests**

```bash
pytest dashboard/backend/tests/test_strategy_store.py -v
```

Expected: 3 PASSED. (These pin *existing* SQLite behavior — they must be green before the Postgres twin is written; a failure here means the retry loop was misread, stop and re-check `repository.py:95-128`.)

- [ ] **Step 3: Write the failing dispatch + Postgres tests**

Create `dashboard/backend/tests/test_strategy_store_postgres.py`:

```python
"""PostgresStrategyStore tests.

Dispatch tests need no live Postgres. Behavioral tests run only when
TEST_POSTGRES_URL is set (see test_users_postgres.py's docstring for the
docker recipe). The collision tests mirror test_strategy_store.py exactly:
the Postgres retry loop is structurally different (ON CONFLICT DO NOTHING +
rowcount, because a UniqueViolation would abort the transaction) and must
behave identically to SQLite's catch-and-retry.
"""

import logging
import os

import pytest

TEST_POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")

pg_only = pytest.mark.skipif(
    not TEST_POSTGRES_URL,
    reason="TEST_POSTGRES_URL not set; skipping live-Postgres tests",
)


# --- dispatch tests ----------------------------------------------------------

def test_build_strategy_store_defaults_to_sqlite(monkeypatch, caplog):
    import dashboard.backend.domain.strategies.repository as strategies_module

    monkeypatch.delenv("DATABASE_URL", raising=False)
    with caplog.at_level(
        logging.INFO, logger="dashboard.backend.domain.strategies.repository"
    ):
        store = strategies_module._build_strategy_store()
    assert isinstance(store, strategies_module.StrategyStore)
    assert "strategy_store backend: sqlite (ephemeral on Render)" in caplog.text


def test_build_strategy_store_picks_postgres_when_url_set(monkeypatch):
    import dashboard.backend.domain.strategies.repository as strategies_module
    import dashboard.backend.domain.strategies.repository_postgres as strategies_pg_module

    created = {}

    class FakePostgresStrategyStore:
        def __init__(self, database_url):
            created["database_url"] = database_url

    monkeypatch.setattr(
        strategies_pg_module, "PostgresStrategyStore", FakePostgresStrategyStore
    )
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/db")

    store = strategies_module._build_strategy_store()

    assert isinstance(store, FakePostgresStrategyStore)
    assert created["database_url"] == "postgresql://fake/db"


# --- live-Postgres behavioral tests ------------------------------------------

@pytest.fixture
def pg_strategy_store():
    from dashboard.backend.domain.strategies.repository_postgres import (
        PostgresStrategyStore,
    )

    store = PostgresStrategyStore(TEST_POSTGRES_URL)
    with store._get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM strategies")
    yield store


@pg_only
def test_create_get_set_last_run_postgres(pg_strategy_store):
    created = pg_strategy_store.create(
        prompt="buy the dip", description="  classic  ", owner="discord:123"
    )
    assert len(created["code"]) == 8
    assert created["description"] == "classic"
    assert created["last_run_id"] is None

    fetched = pg_strategy_store.get(created["code"])
    assert fetched == created
    assert pg_strategy_store.get("missing0") is None
    assert pg_strategy_store.get("") is None

    updated = pg_strategy_store.set_last_run(created["code"], "run_abc")
    assert updated["last_run_id"] == "run_abc"
    assert updated["last_run_at"] is not None
    assert pg_strategy_store.set_last_run("missing0", "run_abc") is None

    with pytest.raises(ValueError):
        pg_strategy_store.create(prompt="   ")


@pg_only
def test_create_retries_past_a_code_collision_postgres(pg_strategy_store, monkeypatch):
    import dashboard.backend.domain.strategies.repository_postgres as strategies_pg_module

    first = pg_strategy_store.create(prompt="first strategy")

    codes = iter([first["code"], "fresh456"])
    monkeypatch.setattr(
        strategies_pg_module.secrets, "token_hex", lambda nbytes: next(codes)
    )

    second = pg_strategy_store.create(prompt="second strategy")
    assert second["code"] == "fresh456"
    assert pg_strategy_store.get(first["code"])["prompt"] == "first strategy"


@pg_only
def test_create_widens_code_space_after_20_collisions_postgres(
    pg_strategy_store, monkeypatch
):
    import dashboard.backend.domain.strategies.repository_postgres as strategies_pg_module

    first = pg_strategy_store.create(prompt="first strategy")

    calls = {"n": 0}

    def fake_token_hex(nbytes):
        calls["n"] += 1
        if calls["n"] <= 20:
            return first["code"]
        return "w" * 16

    monkeypatch.setattr(strategies_pg_module.secrets, "token_hex", fake_token_hex)

    second = pg_strategy_store.create(prompt="second strategy")
    assert second["code"] == "w" * 16
    assert calls["n"] == 21


@pg_only
def test_create_raises_when_even_widened_code_collides_postgres(
    pg_strategy_store, monkeypatch
):
    import dashboard.backend.domain.strategies.repository_postgres as strategies_pg_module

    first = pg_strategy_store.create(prompt="first strategy")

    monkeypatch.setattr(
        strategies_pg_module.secrets, "token_hex", lambda nbytes: first["code"]
    )

    with pytest.raises(RuntimeError):
        pg_strategy_store.create(prompt="second strategy")
```

- [ ] **Step 4: Run to verify the dispatch tests fail**

```bash
pytest dashboard/backend/tests/test_strategy_store_postgres.py -v
```

Expected: `test_build_strategy_store_defaults_to_sqlite` FAILS with `AttributeError` (no `_build_strategy_store`); the picks-postgres test FAILS with `ModuleNotFoundError`; `@pg_only` skip.

- [ ] **Step 5: Create `dashboard/backend/domain/strategies/repository_postgres.py`**

```python
"""Postgres-backed StrategyStore implementation.

Selected instead of the default SQLite StrategyStore when DATABASE_URL is set
(see repository.py's _build_strategy_store). Method surface and behavior are
identical to StrategyStore, with one structural difference: the share-code
retry loop uses ``INSERT ... ON CONFLICT (code) DO NOTHING`` and checks
``cursor.rowcount`` instead of catching IntegrityError. In Postgres a
UniqueViolation aborts the whole transaction (every later statement on the
connection raises InFailedSqlTransaction), so SQLite's catch-and-retry on one
connection cannot be ported literally -- it would 500 on the first real
collision. Retry count, code-space widening, and the RuntimeError fallback
are preserved exactly.
"""

from __future__ import annotations

import secrets
from typing import Any, Optional

import psycopg
from psycopg.rows import dict_row

from dashboard.backend.domain.strategies.repository import (
    _CODE_LENGTH,
    _now_iso,
    _public,
)


class PostgresStrategyStore:
    """Persist free-form strategy prompts, backed by Postgres."""

    def __init__(self, database_url: str):
        self.database_url = database_url
        self._init_schema()

    def _get_connection(self) -> psycopg.Connection:
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def _init_schema(self) -> None:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS strategies (
                        code TEXT PRIMARY KEY,
                        prompt TEXT NOT NULL,
                        description TEXT,
                        source TEXT,
                        owner TEXT,
                        created_at TEXT,
                        last_run_id TEXT,
                        last_run_at TEXT
                    )
                    """
                )

    def create(
        self,
        *,
        prompt: str,
        description: Optional[str] = None,
        source: Optional[str] = None,
        owner: Optional[str] = None,
    ) -> dict[str, Any]:
        cleaned = (prompt or "").strip()
        if not cleaned:
            raise ValueError("Strategy prompt cannot be empty.")
        desc = (description or "").strip() or None
        now = _now_iso()
        with self._get_connection() as conn:
            with conn.cursor() as cur:

                def _insert(candidate: str) -> bool:
                    # ON CONFLICT DO NOTHING + rowcount instead of catching
                    # UniqueViolation: an aborted transaction would poison the
                    # connection for every retry (see module docstring).
                    cur.execute(
                        "INSERT INTO strategies "
                        "(code, prompt, description, source, owner, created_at, last_run_id, last_run_at) "
                        "VALUES (%s, %s, %s, %s, %s, %s, NULL, NULL) "
                        "ON CONFLICT (code) DO NOTHING",
                        (candidate, cleaned, desc, source or None, owner or None, now),
                    )
                    return cur.rowcount == 1

                code = None
                for _ in range(20):
                    candidate = secrets.token_hex(_CODE_LENGTH // 2)
                    if _insert(candidate):
                        code = candidate
                        break
                if code is None:
                    # Astronomically unlikely: widen the code space (64 bits) and
                    # try once more, matching the SQLite store's graceful fallback
                    # rather than surfacing a 500.
                    candidate = secrets.token_hex(_CODE_LENGTH)
                    if not _insert(candidate):
                        raise RuntimeError("Could not allocate a unique strategy code")
                    code = candidate
                cur.execute("SELECT * FROM strategies WHERE code = %s", (code,))
                row = cur.fetchone()
                return _public(row)

    def get(self, code: str) -> Optional[dict[str, Any]]:
        if not code:
            return None
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM strategies WHERE code = %s", (code,))
                row = cur.fetchone()
        return _public(row) if row else None

    def set_last_run(self, code: str, run_id: str) -> Optional[dict[str, Any]]:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE strategies SET last_run_id = %s, last_run_at = %s "
                    "WHERE code = %s RETURNING *",
                    (run_id, _now_iso(), code),
                )
                row = cur.fetchone()
        return _public(row) if row else None
```

- [ ] **Step 6: Add the factory to `dashboard/backend/domain/strategies/repository.py`**

Add `import logging` and `import os` to the stdlib import block at the top, and a module logger after the imports (before `_CODE_LENGTH`):

```python
logger = logging.getLogger(__name__)
```

Replace `strategy_store = StrategyStore()` (line 156) with:

```python
def _build_strategy_store():
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        from dashboard.backend.domain.strategies.repository_postgres import (
            PostgresStrategyStore,
        )

        logger.info("strategy_store backend: postgres")
        return PostgresStrategyStore(database_url)
    logger.info("strategy_store backend: sqlite (ephemeral on Render)")
    return StrategyStore()


strategy_store = _build_strategy_store()
```

Leave the module-level `create_strategy` / `get_strategy` / `set_last_run` wrappers below it untouched — they delegate through the singleton name.

- [ ] **Step 7: Run tests to verify they pass**

```bash
pytest dashboard/backend/tests/test_strategy_store.py dashboard/backend/tests/test_strategy_store_postgres.py dashboard/backend/tests/test_strategies_api.py -v
```

Expected: SQLite collision tests + dispatch tests + existing strategies API tests all PASS; `@pg_only` skip (or PASS with live Postgres).

- [ ] **Step 8: Commit**

```bash
git add dashboard/backend/domain/strategies/repository_postgres.py dashboard/backend/domain/strategies/repository.py dashboard/backend/tests/test_strategy_store.py dashboard/backend/tests/test_strategy_store_postgres.py
git commit -m "feat: Postgres strategy store behind DATABASE_URL"
```

---

### Task 6: Config & developer-docs surface

No code, no tests — documentation the deploy depends on. (User-facing hosted docs are explicitly out of scope for this branch; see the spec's follow-ups section.)

**Files:**
- Modify: `.env.example` (after the `USERS_DATABASE_URL` block, lines 76-83)
- Modify: `render.yaml` (envVars list)
- Modify: `CLAUDE.md` ("Environment & credentials" section and the account-persistence gotcha)

**Interfaces:**
- Consumes: the factory behavior from Tasks 2-5 (must describe it accurately).
- Produces: nothing programmatic.

- [ ] **Step 1: Document `DATABASE_URL` in `.env.example`**

Insert after the `# USERS_DATABASE_URL=postgresql://user:password@host/dbname` line:

```bash
# User-created content (optional). When set, agents, agent versions, and
# strategies are stored in this Postgres database instead of the local SQLite
# file above -- required on ephemeral hosts (Render free tier) where
# DATABASE_PATH resets on every deploy, deleting every registered agent and
# invalidating every issued agent API key. Point it at the SAME database as
# USERS_DATABASE_URL so user->agent ownership stays joinable (and when
# USERS_DATABASE_URL is unset, user accounts fall back to this URL too).
# Use a pooled connection string (e.g. Neon's "-pooler" host) since each
# store call opens a new connection. Leave unset for local dev.
# DATABASE_URL=postgresql://user:password@host/dbname
```

- [ ] **Step 2: Add `DATABASE_URL` to `render.yaml` as documentation**

In the `envVars` list, after the `DATABASE_PATH` entry, add:

```yaml
      # Durable Postgres for user-created content (users fall back to it when
      # USERS_DATABASE_URL is unset). Set in the Render dashboard BEFORE
      # merging the feature -- this yaml is documentation, not the mechanism
      # (prod does not sync from it; see CLAUDE.md "Prod deploy reality").
      - key: DATABASE_URL
        sync: false
```

- [ ] **Step 3: Update `CLAUDE.md`**

In the **Environment & credentials** section, after the `USERS_DATABASE_URL` bullet, add:

```markdown
- `DATABASE_URL` (optional): when set, agents (`external_agents`), agent versions, and strategies are stored in this Postgres database instead of `DATABASE_PATH` SQLite (factories in each store module, cloned from `_build_user_store()`; Postgres twins in `*_postgres.py` siblings). It is also the users-store fallback when `USERS_DATABASE_URL` is unset. Set it in the **Render dashboard before merging** anything that depends on it (unset silently selects ephemeral SQLite; each factory logs `<store> backend: ...` at startup). Point it at the same Neon DB as `USERS_DATABASE_URL`, pooled (`-pooler`) URL. Leave unset for local dev/tests.
```

In the **Gotchas** section, extend the user-accounts bullet (the one starting "**User accounts were silently lost on every prod redeploy until 2026-07**") by appending to it:

```markdown
The same fix was extended to agents, agent versions, and strategies in 2026-07 via `DATABASE_URL` (see `docs/superpowers/specs/2026-07-15-agent-strategy-persistence-design.md`) — before that, every registered agent and issued API key died on each deploy, breaking all SDK/Discord integrations, with `resolve_api_key()` as the sole auth path for `/api/v1` and `/api/v2`.
```

- [ ] **Step 4: Verify nothing broke**

```bash
pytest dashboard/backend/tests/ -q
```

Expected: green (docs-only change; this is a cheap regression tripwire before commit).

- [ ] **Step 5: Commit**

```bash
git add .env.example render.yaml CLAUDE.md
git commit -m "docs: document DATABASE_URL config surface"
```

---

### Task 7: Full-suite verification

**Files:** none (verification only).

**Interfaces:**
- Consumes: everything above.
- Produces: a green branch ready for PR + review.

- [ ] **Step 1: Clear stale bytecode (known phantom-failure source)**

```bash
rm -rf dashboard/backend/engines dashboard/backend/services
find dashboard -name __pycache__ -type d -prune -exec rm -rf {} +
```

- [ ] **Step 2: Run the full backend suite**

```bash
pytest dashboard/backend/tests/ -v 2>&1 | tail -30
```

Expected: everything passes; the only skips are the `@pg_only` tests (+ any pre-existing `importorskip('discord')` skips). Any failure is a real regression — fix before proceeding.

- [ ] **Step 3 (optional but recommended): Run the `@pg_only` tier against a throwaway Postgres**

If docker is available:

```bash
docker run --rm -d --name atl-pg-test -e POSTGRES_PASSWORD=test -e POSTGRES_DB=atl_test -p 5433:5432 postgres:16-alpine
sleep 3
TEST_POSTGRES_URL=postgresql://postgres:test@localhost:5433/atl_test pytest \
  dashboard/backend/tests/test_agent_store_postgres.py \
  dashboard/backend/tests/test_strategy_store_postgres.py \
  dashboard/backend/tests/test_users_postgres.py -v
docker stop atl-pg-test
```

Expected: all `@pg_only` tests PASS (none skipped). If docker is unavailable, note it in the PR body — the live tier then runs at rollout verification instead.

- [ ] **Step 4: Confirm the committed seed DB was not mutated**

```bash
git status --short dashboard/storage/data/backtest.db
```

Expected: no output (conftest isolates `DATABASE_PATH`; if the file shows as modified, a test imported a store before conftest ran — investigate, `git checkout -- dashboard/storage/data/backtest.db`, and fix before PR).

---

## Deploy-time steps (NOT part of this branch — from the spec's Rollout section)

Recorded here so the PR body can reference them; they happen in the Render dashboard and GitHub, not in code:

1. Set `DATABASE_URL` in the **Render dashboard** (same Neon database as `USERS_DATABASE_URL`, pooled `-pooler` URL) — **before** merging.
2. Merge the PR; CI auto-deploys on green main.
3. Confirm the four `... backend: postgres` startup log lines in Render logs.
4. Live verification: create an agent → trigger a redeploy → agent still lists and its API key still resolves.
5. Recreate the built-in agents once via the normal API; they persist thereafter.
