"""External agent backtest API — hourly step loop with 10s decision timeout."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from external_backtest_service import (
    get_current_step,
    get_status,
    start_backtest,
    submit_decisions,
)

router = APIRouter(prefix="/v1/backtest", tags=["external-backtest"])


class StartBacktestRequest(BaseModel):
    start_date: str = Field(examples=["2026-04-15"])
    end_date: str = Field(examples=["2026-04-16"])
    agent_name: str = Field(default="external-agent", min_length=1, max_length=100)
    model_name: str = Field(default="local-model", min_length=1, max_length=100)
    mode: str = Field(default="safe_trading", pattern="^(safe_trading|buy_and_hold)$")


class TradingActionItem(BaseModel):
    action: str
    symbol: str
    confidence: float
    reasoning: str
    position_size: int
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None


class SubmitDecisionsRequest(BaseModel):
    actions: List[TradingActionItem]


def _require_session(session_id: Optional[str]) -> str:
    if not session_id:
        raise HTTPException(status_code=400, detail="Missing X-Session-Id header")
    return session_id


@router.post("/start")
async def api_start_backtest(
    body: StartBacktestRequest,
    x_session_id: Optional[str] = Header(None),
):
    """
    Start an external-agent backtest.

    Loads Alpaca data, then waits for decisions at each trading hour.
    Use the same X-Session-Id as the dashboard to see results on the website.
    """
    session_id = _require_session(x_session_id)
    result = start_backtest(
        session_id=session_id,
        agent_name=body.agent_name,
        model_name=body.model_name,
        start_date=body.start_date,
        end_date=body.end_date,
        mode=body.mode,
    )
    if result.get("status") == "failed":
        raise HTTPException(status_code=500, detail=result.get("error", "Backtest failed to start"))
    return result


@router.get("/{backtest_id}/steps/current")
async def api_get_current_step(
    backtest_id: str,
    x_session_id: Optional[str] = Header(None),
):
    """Get market context for the current hour. Auto-holds after 10s without a decision."""
    _require_session(x_session_id)
    step = get_current_step(backtest_id)
    if step is None:
        raise HTTPException(status_code=404, detail="Backtest not found")
    return step


@router.post("/{backtest_id}/steps/current/decisions")
async def api_submit_decisions(
    backtest_id: str,
    body: SubmitDecisionsRequest,
    x_session_id: Optional[str] = Header(None),
):
    """
    Submit trading decisions for the current hour.

    Body format:
    {"actions": [{"action":"buy|sell|hold","symbol":"AAPL","confidence":0.8,...}]}
    """
    _require_session(x_session_id)
    payload: Dict[str, Any] = {"actions": [a.model_dump() for a in body.actions]}
    result = submit_decisions(backtest_id, payload)
    if result is None:
        raise HTTPException(status_code=404, detail="Backtest not found")
    if not result.get("accepted") and result.get("error") == "step_already_closed":
        raise HTTPException(status_code=409, detail=result)
    return result


@router.get("/{backtest_id}/status")
async def api_backtest_status(
    backtest_id: str,
    x_session_id: Optional[str] = Header(None),
):
    """Poll backtest progress."""
    _require_session(x_session_id)
    status = get_status(backtest_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Backtest not found")
    return status
