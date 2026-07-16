"""The suite must never see backend-selecting env vars from the developer's shell.

conftest.py pops them at import time -- before any backend module is imported,
which is the only moment that works, since the store singletons are built during
that import.

Scope, honestly: these tests assert the vars are absent *while the suite runs*.
They cannot prove the pop happens at conftest import time rather than in a
fixture, so they would stay green under a refactor that moved it somewhere
too late to matter. What they do catch is the pop being dropped outright, which
is the realistic regression. The import-time placement is guarded by the comment
at the pop itself.

Why this matters beyond "don't touch prod data": once the store factories exist,
an ambient CONTENT_DATABASE_URL doesn't merely redirect writes -- it swaps the singletons
for Postgres twins that have no .db_path, breaking the existing tests that assert
on it (tests/domain/agents/test_repository_move.py:39-40 and
tests/domain/strategies/test_strategy_store.py:42-43).
"""

import os


def test_users_database_url_is_stripped_for_the_suite():
    assert "USERS_DATABASE_URL" not in os.environ


def test_content_database_url_is_stripped_for_the_suite():
    assert "CONTENT_DATABASE_URL" not in os.environ
