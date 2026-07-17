"""PostgresAgentStore / PostgresAgentVersionStore tests.

Two tiers, mirroring test_users_postgres.py:
1. Dispatch-logic tests (no live Postgres needed) - verify the module
   factories pick the right store class based on CONTENT_DATABASE_URL.
2. Behavioral tests against a real Postgres - skipped unless
   TEST_POSTGRES_URL is set. Point it at a throwaway database, e.g.:
     docker run --rm -e POSTGRES_PASSWORD=test -e POSTGRES_DB=atl_test \
       -p 5433:5432 postgres:16-alpine
     export TEST_POSTGRES_URL=postgresql://postgres:test@localhost:5433/atl_test

Do NOT copy the raw-SQL fixture pattern from test_v2_http_runs.py /
test_v2_auth.py (SQLite-only `?` placeholders); use public store methods.
"""

import os

import pytest

TEST_POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")

pg_only = pytest.mark.skipif(
    not TEST_POSTGRES_URL,
    reason="TEST_POSTGRES_URL not set; skipping live-Postgres tests",
)


# --- dispatch tests (agent store) -------------------------------------------

def test_build_agent_store_defaults_to_sqlite(monkeypatch, capsys):
    import dashboard.backend.domain.agents.repository as repo_module

    monkeypatch.delenv("CONTENT_DATABASE_URL", raising=False)
    store = repo_module._build_agent_store()
    assert isinstance(store, repo_module.AgentStore)
    assert "agent_store backend: sqlite (ephemeral on Render)" in capsys.readouterr().out


def test_build_agent_store_picks_postgres_when_url_set(monkeypatch, capsys):
    import dashboard.backend.domain.agents.repository as repo_module
    import dashboard.backend.domain.agents.repository_postgres as repo_pg_module

    created = {}

    class FakePostgresAgentStore:
        def __init__(self, database_url):
            created["database_url"] = database_url

    monkeypatch.setattr(repo_pg_module, "PostgresAgentStore", FakePostgresAgentStore)
    monkeypatch.setenv("CONTENT_DATABASE_URL", "postgresql://fake/db")

    store = repo_module._build_agent_store()

    assert isinstance(store, FakePostgresAgentStore)
    assert created["database_url"] == "postgresql://fake/db"
    # capsys (the factory print()s) and the target is named -- see Task 3.
    assert "agent_store backend: postgres (fake/db)" in capsys.readouterr().out


def test_build_agent_store_never_prints_the_credentials(monkeypatch, capsys):
    import dashboard.backend.domain.agents.repository as repo_module
    import dashboard.backend.domain.agents.repository_postgres as repo_pg_module

    class FakePostgresAgentStore:
        def __init__(self, database_url):
            pass

    monkeypatch.setattr(repo_pg_module, "PostgresAgentStore", FakePostgresAgentStore)
    monkeypatch.setenv("CONTENT_DATABASE_URL", "postgresql://admin:sup3r-s3cret@host/db")

    repo_module._build_agent_store()

    out = capsys.readouterr().out
    assert "sup3r-s3cret" not in out
    assert "agent_store backend: postgres (host/db)" in out


def test_unreachable_postgres_agent_store_raises_instead_of_falling_back():
    """Fail loud: a set-but-unreachable URL must not silently degrade to SQLite.

    The only tier that runs PostgresAgentStore.__init__ (and therefore its
    _init_schema DDL path) without a live server -- the dispatch tests above
    monkeypatch the class away. A closed port refuses instantly; connect_timeout
    stops a DROP-style firewall from hanging the suite.
    """
    import psycopg

    from dashboard.backend.domain.agents.repository_postgres import PostgresAgentStore

    with pytest.raises(psycopg.OperationalError):
        PostgresAgentStore("postgresql://u:p@127.0.0.1:1/nope?connect_timeout=2")


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
