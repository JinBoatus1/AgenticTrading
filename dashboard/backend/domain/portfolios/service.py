"""Thin portfolio service over the content-DB store."""

from __future__ import annotations

from typing import Any, Dict

from dashboard.backend.domain.backtesting.constants import DEFAULT_PORTFOLIO_EQUITY
from dashboard.backend.domain.portfolios.repository import portfolio_store


class PortfolioService:
    def get_or_create_portfolio(self, owner_user_id: int) -> Dict[str, Any]:
        return portfolio_store.get_or_create(
            int(owner_user_id),
            equity=DEFAULT_PORTFOLIO_EQUITY,
        )


portfolio_service = PortfolioService()
