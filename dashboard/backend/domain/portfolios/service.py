"""Portfolio service: bootstrap + allocate / reclaim against agent sleeves."""

from __future__ import annotations

from typing import Any, Dict, Optional

from dashboard.backend.domain.backtesting.constants import (
    DEFAULT_PORTFOLIO_EQUITY,
    MAX_AGENT_CASH_ALLOCATION,
)
from dashboard.backend.domain.portfolios.repository import (
    CashExceedsEquityError,
    InsufficientCashError,
    portfolio_store,
)

# Re-export store errors alongside service-level InsufficientSleeveError.


class InsufficientSleeveError(ValueError):
    """Raised when reclaim exceeds the agent's cash_allocation sleeve."""


class PortfolioService:
    def get_or_create_portfolio(self, owner_user_id: int) -> Dict[str, Any]:
        return portfolio_store.get_or_create(
            int(owner_user_id),
            equity=DEFAULT_PORTFOLIO_EQUITY,
        )

    def credit(self, owner_user_id: int, amount: float) -> Dict[str, Any]:
        """Return ``amount`` to unallocated cash."""
        if amount < 0:
            raise ValueError("credit amount must be >= 0")
        if amount == 0:
            return self.get_or_create_portfolio(owner_user_id)
        return portfolio_store.adjust_cash_available(int(owner_user_id), float(amount))

    def debit(self, owner_user_id: int, amount: float) -> Dict[str, Any]:
        """Take ``amount`` from unallocated cash."""
        if amount < 0:
            raise ValueError("debit amount must be >= 0")
        if amount == 0:
            return self.get_or_create_portfolio(owner_user_id)
        return portfolio_store.adjust_cash_available(int(owner_user_id), -float(amount))

    def allocate_to_agent(
        self,
        *,
        owner_user_id: int,
        agent: Dict[str, Any],
        amount: float,
    ) -> Dict[str, Any]:
        """Move ``amount`` from unallocated → agent.cash_allocation."""
        from dashboard.backend.domain.agents.repository import agent_store

        amount_f = float(amount)
        if amount_f <= 0:
            raise ValueError("allocate amount must be > 0")
        sleeve = float(agent.get("cash_allocation") or 0)
        new_sleeve = sleeve + amount_f
        if new_sleeve > float(MAX_AGENT_CASH_ALLOCATION) + 1e-9:
            raise ValueError(
                f"Agent allocation would exceed max "
                f"({MAX_AGENT_CASH_ALLOCATION:,.0f})."
            )

        portfolio = self.debit(owner_user_id, amount_f)
        try:
            updated = agent_store.update_agent(
                agent["agent_id"],
                cash_allocation=new_sleeve,
            )
            if not updated:
                raise RuntimeError("agent disappeared during allocate")
        except Exception:
            # Compensating credit so the ledger is not left short.
            self.credit(owner_user_id, amount_f)
            raise
        return {"portfolio": portfolio, "agent": updated}

    def reclaim_from_agent(
        self,
        *,
        owner_user_id: int,
        agent: Dict[str, Any],
        amount: float,
    ) -> Dict[str, Any]:
        """Move ``amount`` from agent.cash_allocation → unallocated."""
        from dashboard.backend.domain.agents.repository import agent_store

        amount_f = float(amount)
        if amount_f <= 0:
            raise ValueError("reclaim amount must be > 0")
        sleeve = float(agent.get("cash_allocation") or 0)
        if amount_f > sleeve + 1e-9:
            raise InsufficientSleeveError(
                f"Insufficient agent allocation "
                f"(have {sleeve:.2f}, need {amount_f:.2f})."
            )
        new_sleeve = max(sleeve - amount_f, 0.0)

        updated = agent_store.update_agent(
            agent["agent_id"],
            cash_allocation=new_sleeve,
        )
        if not updated:
            raise RuntimeError("agent disappeared during reclaim")
        try:
            portfolio = self.credit(owner_user_id, amount_f)
        except Exception:
            agent_store.update_agent(agent["agent_id"], cash_allocation=sleeve)
            raise
        return {"portfolio": portfolio, "agent": updated}

    def set_agent_allocation(
        self,
        *,
        owner_user_id: int,
        agent: Dict[str, Any],
        new_amount: float,
    ) -> Dict[str, Any]:
        """Set absolute sleeve; allocate or reclaim the delta."""
        new_f = float(new_amount)
        if new_f < 0:
            raise ValueError("allocation must be >= 0")
        if new_f > float(MAX_AGENT_CASH_ALLOCATION) + 1e-9:
            raise ValueError(
                f"Agent allocation would exceed max "
                f"({MAX_AGENT_CASH_ALLOCATION:,.0f})."
            )
        old = float(agent.get("cash_allocation") or 0)
        delta = new_f - old
        if abs(delta) < 1e-9:
            return {
                "portfolio": self.get_or_create_portfolio(owner_user_id),
                "agent": agent,
            }
        if delta > 0:
            return self.allocate_to_agent(
                owner_user_id=owner_user_id, agent=agent, amount=delta
            )
        return self.reclaim_from_agent(
            owner_user_id=owner_user_id, agent=agent, amount=-delta
        )

    def reclaim_all_on_delete(
        self,
        *,
        owner_user_id: Optional[int],
        cash_allocation: Optional[float],
    ) -> Optional[Dict[str, Any]]:
        """Credit the agent's sleeve back to the portfolio (after delete)."""
        if not owner_user_id:
            return None
        sleeve = float(cash_allocation or 0)
        if sleeve <= 0:
            return self.get_or_create_portfolio(int(owner_user_id))
        return self.credit(int(owner_user_id), sleeve)

    def debit_for_new_agent(self, owner_user_id: int, amount: float) -> Dict[str, Any]:
        """Debit unallocated cash before inserting a new funded agent."""
        return self.debit(owner_user_id, float(amount or 0))


portfolio_service = PortfolioService()

# Re-export errors for routers/tests.
__all__ = [
    "CashExceedsEquityError",
    "InsufficientCashError",
    "InsufficientSleeveError",
    "PortfolioService",
    "portfolio_service",
]
