"""Pytest configuration for the dashboard backend test suite.

Phase 0.5 — Isolate the test database.

The backend resolves its SQLite path at *import time*::

    # database.py
    DB_PATH = Path(os.getenv("DATABASE_PATH", str(DEFAULT_DB_PATH)))
    ...
    db = BacktestDatabase()  # built once, against DB_PATH

and every store/repository reads ``DB_PATH`` / ``DEFAULT_DB_PATH`` from that same
module. So pointing ``DATABASE_PATH`` at a fresh temporary file *before any
backend module is imported* isolates the entire data layer in one place.

This module is imported by pytest before the test modules in this directory, so
setting the environment variable here (at import time, not in a fixture)
guarantees it is in effect before ``app`` / ``database`` are first imported.

Guarantees:
* The live database ``dashboard/storage/data/backtest.db`` is never read,
  written, copied, reset, or deleted by the test run.
* Schema creation and migrations run automatically when ``BacktestDatabase`` is
  constructed against the temporary path.
* Production behavior is unchanged: this only affects the pytest process, which
  does not run in production.
"""

import atexit
import os
import shutil
import tempfile

# Create an isolated, empty temporary database BEFORE backend modules import.
_TEST_DB_DIR = tempfile.mkdtemp(prefix="atl_test_db_")
_TEST_DB_PATH = os.path.join(_TEST_DB_DIR, "test_backtest.db")

# Only set it for the test process; never touch the real DATABASE_PATH/live file.
os.environ["DATABASE_PATH"] = _TEST_DB_PATH


@atexit.register
def _cleanup_test_db_dir() -> None:
    """Remove the temporary database directory when the test process exits."""
    shutil.rmtree(_TEST_DB_DIR, ignore_errors=True)
