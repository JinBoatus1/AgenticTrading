"""Postgres-backed PortfolioStore.

Selected when ``CONTENT_DATABASE_URL`` is set (see repository._build_portfolio_store).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import psycopg
from psycopg.rows import dict_row

from dashboard.backend.db_url import require_postgres_url
from dashboard.backend.domain.backtesting.constants import DEFAULT_PORTFOLIO_EQUITY
from dashboard.backend.domain.portfolios.repository import _public_portfolio, _utcnow_iso


class PostgresPortfolioStore:
    """One portfolio row per signed-in user, backed by Postgres."""

    def __init__(self, database_url: str):
        self.database_url = require_postgres_url(database_url)
        self._init_schema()

    def _get_connection(self) -> psycopg.Connection:
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def _init_schema(self) -> None:
        # owner_user_id is a plain INTEGER with no FK to users(id): same
        # rationale as external_agents (split USERS vs CONTENT databases).
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_portfolios (
                        owner_user_id INTEGER PRIMARY KEY,
                        equity DOUBLE PRECISION NOT NULL,
                        cash_available DOUBLE PRECISION NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )

    def get(self, owner_user_id: int) -> Optional[Dict[str, Any]]:
        self._init_schema()
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM user_portfolios WHERE owner_user_id = %s",
                    (int(owner_user_id),),
                )
                row = cur.fetchone()
        return _public_portfolio(row) if row else None

    def create(
        self,
        owner_user_id: int,
        *,
        equity: float = DEFAULT_PORTFOLIO_EQUITY,
    ) -> Dict[str, Any]:
        self._init_schema()
        now = _utcnow_iso()
        equity_f = float(equity)
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_portfolios (
                        owner_user_id, equity, cash_available, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s)
                    """,
                    (int(owner_user_id), equity_f, equity_f, now, now),
                )
        created = self.get(owner_user_id)
        assert created is not None
        return created

    def get_or_create(
        self,
        owner_user_id: int,
        *,
        equity: float = DEFAULT_PORTFOLIO_EQUITY,
    ) -> Dict[str, Any]:
        existing = self.get(owner_user_id)
        if existing is not None:
            return existing
        try:
            return self.create(owner_user_id, equity=equity)
        except psycopg.errors.UniqueViolation:
            raced = self.get(owner_user_id)
            if raced is None:
                raise
            return raced
