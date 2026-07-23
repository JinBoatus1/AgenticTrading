"""PostgresPortfolioStore tests.

Dispatch tests need no live Postgres. Behavioral tests run only when
TEST_POSTGRES_URL is set (see test_users_postgres.py's docstring for the
docker recipe).

This tier is not optional cover: prod sets CONTENT_DATABASE_URL, so the
Postgres twin -- not the SQLite default the rest of the suite exercises -- is
the only implementation real users ever hit. Without these tests the whole
file ships unexecuted (the exact failure test_ci_postgres_wired.py exists to
make loud).
"""

import os

import pytest

from dashboard.backend.domain.backtesting.constants import DEFAULT_PORTFOLIO_EQUITY
from dashboard.backend.tests._postgres_testing import require_local_postgres_url

TEST_POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")

pg_only = pytest.mark.skipif(
    not TEST_POSTGRES_URL,
    reason="TEST_POSTGRES_URL not set; skipping live-Postgres tests",
)


# --- dispatch tests ----------------------------------------------------------

def test_build_portfolio_store_defaults_to_sqlite(monkeypatch, capsys):
    import dashboard.backend.domain.portfolios.repository as repo_module

    monkeypatch.delenv("CONTENT_DATABASE_URL", raising=False)
    store = repo_module._build_portfolio_store()
    assert isinstance(store, repo_module.PortfolioStore)
    assert (
        "portfolio_store backend: sqlite (ephemeral on Render)"
        in capsys.readouterr().out
    )


def test_build_portfolio_store_picks_postgres_when_url_set(monkeypatch, capsys):
    import dashboard.backend.domain.portfolios.repository as repo_module
    import dashboard.backend.domain.portfolios.repository_postgres as repo_pg_module

    created = {}

    class FakePostgresPortfolioStore:
        def __init__(self, database_url):
            created["database_url"] = database_url

    monkeypatch.setattr(
        repo_pg_module, "PostgresPortfolioStore", FakePostgresPortfolioStore
    )
    monkeypatch.setenv("CONTENT_DATABASE_URL", "postgresql://fake/db")

    store = repo_module._build_portfolio_store()

    assert isinstance(store, FakePostgresPortfolioStore)
    assert created["database_url"] == "postgresql://fake/db"
    assert "portfolio_store backend: postgres (fake/db)" in capsys.readouterr().out


def test_build_portfolio_store_ignores_users_database_url(monkeypatch, capsys):
    """See the agent-store twin of this test (test_agent_store_postgres.py)."""
    import dashboard.backend.domain.portfolios.repository as repo_module

    monkeypatch.delenv("CONTENT_DATABASE_URL", raising=False)
    monkeypatch.setenv("USERS_DATABASE_URL", "postgresql://fake/users")

    store = repo_module._build_portfolio_store()

    assert isinstance(store, repo_module.PortfolioStore)
    assert (
        "portfolio_store backend: sqlite (ephemeral on Render)"
        in capsys.readouterr().out
    )


def test_unreachable_postgres_portfolio_store_raises_instead_of_falling_back():
    """Fail loud — see the agent-store twin of this test."""
    import psycopg

    from dashboard.backend.domain.portfolios.repository_postgres import (
        PostgresPortfolioStore,
    )

    with pytest.raises(psycopg.OperationalError):
        PostgresPortfolioStore("postgresql://u:p@127.0.0.1:1/nope?connect_timeout=2")


def test_malformed_url_is_rejected_before_psycopg_can_echo_it():
    """See the agent-store twin of this test (test_agent_store_postgres.py)."""
    from dashboard.backend.domain.portfolios.repository_postgres import (
        PostgresPortfolioStore,
    )

    with pytest.raises(ValueError) as excinfo:
        PostgresPortfolioStore('"postgresql://u:sup3r-s3cret@ep-x.neon.tech/atl"')
    assert "sup3r-s3cret" not in str(excinfo.value)


# --- live-Postgres behavioral tests ------------------------------------------

@pytest.fixture
def pg_portfolio_store():
    require_local_postgres_url(TEST_POSTGRES_URL)
    from dashboard.backend.domain.portfolios.repository_postgres import (
        PostgresPortfolioStore,
    )

    store = PostgresPortfolioStore(TEST_POSTGRES_URL)
    with store._get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM user_portfolios")
    yield store


@pg_only
def test_get_or_create_bootstraps_10k_and_is_idempotent_postgres(pg_portfolio_store):
    assert pg_portfolio_store.get(7) is None

    first = pg_portfolio_store.get_or_create(7)
    assert first["owner_user_id"] == 7
    assert first["equity"] == float(DEFAULT_PORTFOLIO_EQUITY)
    assert first["cash_available"] == float(DEFAULT_PORTFOLIO_EQUITY)
    assert first["allocated"] == 0.0

    assert pg_portfolio_store.get_or_create(7) == first


@pg_only
def test_portfolios_are_isolated_per_user_postgres(pg_portfolio_store):
    """One row per user, and no user's read can reach another's row."""
    alice = pg_portfolio_store.get_or_create(1)
    bob = pg_portfolio_store.create(2, equity=250.0)

    assert alice["owner_user_id"] == 1
    assert bob["owner_user_id"] == 2
    assert bob["equity"] == 250.0
    # Bootstrapping Bob must not have touched Alice's balance.
    assert pg_portfolio_store.get(1) == alice
    assert pg_portfolio_store.get(999) is None


@pg_only
def test_get_or_create_survives_a_concurrent_bootstrap_postgres(pg_portfolio_store):
    """Two workers can both read 'no row' and both INSERT; the loser must not 500.

    A UniqueViolation aborts the surrounding transaction in Postgres, so this
    path is structurally different from SQLite's IntegrityError and has to be
    exercised on the real driver.
    """
    pg_portfolio_store.create(42)  # the winner's row

    calls = {"n": 0}
    real_get = pg_portfolio_store.get

    def blind_on_first_call(owner_user_id):
        calls["n"] += 1
        return None if calls["n"] == 1 else real_get(owner_user_id)

    pg_portfolio_store.get = blind_on_first_call

    raced = pg_portfolio_store.get_or_create(42)
    assert raced["owner_user_id"] == 42
    assert raced["equity"] == float(DEFAULT_PORTFOLIO_EQUITY)
    assert calls["n"] == 2  # the blind read, then the post-collision re-read


@pg_only
def test_public_payload_matches_the_sqlite_tier_postgres(pg_portfolio_store, tmp_path):
    """Tier parity: the two stores must serialise a portfolio identically.

    The API returns this dict verbatim, so a key that exists on only one tier
    is a contract break visible solely in prod (SQLite is the default here).
    """
    from dashboard.backend.domain.portfolios.repository import PortfolioStore

    sqlite_row = PortfolioStore(db_path=tmp_path / "parity.db").get_or_create(9)
    pg_row = pg_portfolio_store.get_or_create(9)

    assert sorted(pg_row) == sorted(sqlite_row)
    for key in ("owner_user_id", "equity", "cash_available", "allocated"):
        assert pg_row[key] == sqlite_row[key], key
    for key in ("created_at", "updated_at"):
        # SQLite declares TIMESTAMP, Postgres TEXT; both must reach JSON as an
        # ISO-8601 string, not a datetime the encoder would render differently.
        assert isinstance(pg_row[key], str), key
        assert isinstance(sqlite_row[key], str), key
