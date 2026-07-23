"""Account-bound portfolio API (signed-in users only)."""

from fastapi import APIRouter, Depends

from dashboard.backend.api.auth import get_current_user
from dashboard.backend.domain.portfolios.service import portfolio_service

router = APIRouter(prefix="/v1/portfolio", tags=["portfolio"])


@router.get("")
async def get_portfolio(current_user: dict = Depends(get_current_user)):
    """Return the caller's portfolio, bootstrapping at $10k if missing."""
    portfolio = portfolio_service.get_or_create_portfolio(current_user["id"])
    return {"portfolio": portfolio}
