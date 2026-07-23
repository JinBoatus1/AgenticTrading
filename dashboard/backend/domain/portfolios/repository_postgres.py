"""Postgres-backed PortfolioStore.

Selected when ``CONTENT_DATABASE_URL`` is set (see repository._build_portfolio_store).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import psycopg
from psycopg.rows import dict_row

from dashboard.backend.db_url import require_postgres_url
from dashboard.backend.domain.backtesting.constants import DEFAULT_PORTFOLIO_EQUITY
from dashboard.backend.domain.portfolios.repository import (
    CashExceedsEquityError,
    InsufficientCashError,
    _public_portfolio,
    _utcnow_iso,
)


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

    def adjust_cash_available(self, owner_user_id: int, delta: float) -> Dict[str, Any]:
        """Apply ``delta`` to cash_available (negative = allocate, positive = reclaim)."""
        self.get_or_create(owner_user_id)
        uid = int(owner_user_id)
        delta_f = float(delta)
        now = _utcnow_iso()
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT equity, cash_available FROM user_portfolios "
                    "WHERE owner_user_id = %s FOR UPDATE",
                    (uid,),
                )
                row = cur.fetchone()
                if row is None:
                    raise RuntimeError(f"portfolio missing for user {uid}")
                equity = float(row["equity"])
                cash = float(row["cash_available"])
                new_cash = cash + delta_f
                if new_cash < -1e-9:
                    raise InsufficientCashError(
                        f"Insufficient unallocated cash "
                        f"(have {cash:.2f}, need {-delta_f:.2f})."
                    )
                if new_cash > equity + 1e-9:
                    raise CashExceedsEquityError(
                        f"cash_available {new_cash:.2f} would exceed equity {equity:.2f}."
                    )
                new_cash = min(max(new_cash, 0.0), equity)
                cur.execute(
                    """
                    UPDATE user_portfolios
                    SET cash_available = %s, updated_at = %s
                    WHERE owner_user_id = %s
                    """,
                    (new_cash, now, uid),
                )
        updated = self.get(uid)
        assert updated is not None
        return updated
