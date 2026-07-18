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

from dashboard.backend.tests._postgres_testing import require_local_postgres_url

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


def test_build_agent_store_ignores_users_database_url(monkeypatch, capsys):
    """The mirror of test_users_postgres.py's ignores_content_database_url.

    The two vars are scoped per store and neither falls back to the other (spec,
    Decision 2). That was guarded in one direction only -- nothing stopped a
    future "convenience" fallback from quietly binding agents to the *accounts*
    database, which is exactly the kind of one-line change that reads like an
    improvement and keeps the suite green.
    """
    import dashboard.backend.domain.agents.repository as repo_module

    monkeypatch.delenv("CONTENT_DATABASE_URL", raising=False)
    monkeypatch.setenv("USERS_DATABASE_URL", "postgresql://fake/users")

    store = repo_module._build_agent_store()

    assert isinstance(store, repo_module.AgentStore)
    assert "agent_store backend: sqlite (ephemeral on Render)" in capsys.readouterr().out


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


def test_malformed_url_is_rejected_before_psycopg_can_echo_it():
    """A typo'd CONTENT_DATABASE_URL must not put the password in the log.

    psycopg parses anything not starting with postgresql:// as a keyword DSN and
    quotes the whole input back ('missing "=" after "<the entire URL>"'). This
    runs at import time with no try/except, so that message is the boot failure
    and it lands in Render's log. require_postgres_url must therefore be wired
    into __init__ -- testing the helper alone would not catch it being dropped
    from the constructor.
    """
    from dashboard.backend.domain.agents.repository_postgres import PostgresAgentStore

    with pytest.raises(ValueError) as excinfo:
        PostgresAgentStore('"postgresql://u:sup3r-s3cret@ep-x.neon.tech/atl"')
    assert "sup3r-s3cret" not in str(excinfo.value)


# --- live-Postgres behavioral tests (agent store) ---------------------------

@pytest.fixture
def pg_agent_store():
    require_local_postgres_url(TEST_POSTGRES_URL)
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
def test_cash_allocation_round_trips_as_a_float_postgres(pg_agent_store):
    """Pin the feature's only non-TEXT column against a real Postgres.

    Every other @pg_only test leaves cash_allocation NULL, yet service.py
    defaults it to float(DEFAULT_AGENT_CASH_ALLOCATION) when a caller omits it
    -- so every real agent registration writes a float on a column nothing here
    exercised. Declare it TEXT (the type the other 14 columns have) and the whole
    tier still passes; the first prod registration is what finds out.
    """
    created = pg_agent_store.create_agent(name="Funded", cash_allocation=25000.5)
    assert created["cash_allocation"] == 25000.5
    assert isinstance(created["cash_allocation"], float)

    assert pg_agent_store.get_agent(created["agent_id"])["cash_allocation"] == 25000.5

    updated = pg_agent_store.update_agent(created["agent_id"], cash_allocation=100.25)
    assert updated["cash_allocation"] == 100.25

    # _UNSET vs None: omitting it leaves the stored value, passing None clears it.
    assert pg_agent_store.update_agent(created["agent_id"], name="Renamed")[
        "cash_allocation"
    ] == 100.25
    assert pg_agent_store.update_agent(created["agent_id"], cash_allocation=None)[
        "cash_allocation"
    ] is None


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


# --- dispatch tests (agent version store) ------------------------------------

def test_build_agent_version_store_defaults_to_sqlite(monkeypatch, capsys):
    import dashboard.backend.domain.agents.version_repository as vrepo_module

    monkeypatch.delenv("CONTENT_DATABASE_URL", raising=False)
    store = vrepo_module._build_agent_version_store()
    assert isinstance(store, vrepo_module.AgentVersionStore)
    assert (
        "agent_version_store backend: sqlite (ephemeral on Render)"
        in capsys.readouterr().out
    )


def test_build_agent_version_store_picks_postgres_when_url_set(monkeypatch, capsys):
    import dashboard.backend.domain.agents.version_repository as vrepo_module
    import dashboard.backend.domain.agents.version_repository_postgres as vrepo_pg_module

    created = {}

    class FakePostgresAgentVersionStore:
        def __init__(self, database_url):
            created["database_url"] = database_url

    monkeypatch.setattr(
        vrepo_pg_module, "PostgresAgentVersionStore", FakePostgresAgentVersionStore
    )
    monkeypatch.setenv("CONTENT_DATABASE_URL", "postgresql://fake/db")

    store = vrepo_module._build_agent_version_store()

    assert isinstance(store, FakePostgresAgentVersionStore)
    assert created["database_url"] == "postgresql://fake/db"
    assert "agent_version_store backend: postgres (fake/db)" in capsys.readouterr().out


def test_build_agent_version_store_ignores_users_database_url(monkeypatch, capsys):
    """See the agent-store twin of this test above."""
    import dashboard.backend.domain.agents.version_repository as vrepo_module

    monkeypatch.delenv("CONTENT_DATABASE_URL", raising=False)
    monkeypatch.setenv("USERS_DATABASE_URL", "postgresql://fake/users")

    store = vrepo_module._build_agent_version_store()

    assert isinstance(store, vrepo_module.AgentVersionStore)
    assert (
        "agent_version_store backend: sqlite (ephemeral on Render)"
        in capsys.readouterr().out
    )


def test_unreachable_postgres_version_store_raises_instead_of_falling_back():
    """Fail loud — see the agent-store twin of this test above."""
    import psycopg

    from dashboard.backend.domain.agents.version_repository_postgres import (
        PostgresAgentVersionStore,
    )

    with pytest.raises(psycopg.OperationalError):
        PostgresAgentVersionStore("postgresql://u:p@127.0.0.1:1/nope?connect_timeout=2")


def test_malformed_url_is_rejected_before_psycopg_can_echo_it_version_store():
    """See the agent-store twin of this test above."""
    from dashboard.backend.domain.agents.version_repository_postgres import (
        PostgresAgentVersionStore,
    )

    with pytest.raises(ValueError) as excinfo:
        PostgresAgentVersionStore('"postgresql://u:sup3r-s3cret@ep-x.neon.tech/atl"')
    assert "sup3r-s3cret" not in str(excinfo.value)


# --- live-Postgres behavioral tests (agent version store) --------------------

@pytest.fixture
def pg_version_store():
    require_local_postgres_url(TEST_POSTGRES_URL)
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
