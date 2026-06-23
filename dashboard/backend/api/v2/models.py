"""Typed v2 wire contract (spec §5). Source of the auto-generated OpenAPI doc."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from llm_validator import DJIA_30

SCHEMA_VERSION = "2.0"
UNIVERSE_KEY = "djia_30"
UNIVERSE: List[str] = list(DJIA_30)
_UNIVERSE_SET = set(UNIVERSE)


# --- Context envelope ------------------------------------------------------

class NewsSentimentEntry(BaseModel):
    sentiment: str = Field(pattern="^(bullish|bearish|neutral)$")
    score: float = Field(ge=-1.0, le=1.0)
    headline: str
    source: str
    url: str
    age_hours: float = Field(ge=0.0)
    n_articles: int = Field(ge=0)


class PortfolioState(BaseModel):
    cash: float
    positions_value: float
    total_equity: float
    num_positions: int


class HoldingItem(BaseModel):
    shares: float
    entry_price: float
    current_price: float
    position_value: float
    pnl_pct: float


class SignalItem(BaseModel):
    price: float
    rsi: float
    macd: float
    macd_signal: float
    sma20: float
    sma50: float
    bb_upper: float
    bb_lower: float


class ContextEnvelope(BaseModel):
    schema_version: str
    run_id: str
    mode: str
    step_index: int
    total_steps: int
    timestamp: Optional[str] = None
    loop: str  # "lockstep" | "realtime"
    decision_deadline_at: Optional[str] = None
    decision_timeout_seconds: Optional[int] = None
    status: str  # loading | waiting_decision | completed | closed | failed
    universe: List[str]
    portfolio: Optional[PortfolioState] = None
    current_holdings: Dict[str, HoldingItem] = Field(default_factory=dict)
    recent_trades: List[Dict[str, Any]] = Field(default_factory=list)
    top_signals: Dict[str, SignalItem] = Field(default_factory=dict)
    news_sentiment: Dict[str, NewsSentimentEntry] = Field(default_factory=dict)
    news_overview: Optional[str] = None
    decision_format: Optional[Dict[str, Any]] = None


# --- Decision request ------------------------------------------------------

class ActionItem(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    action: str = Field(pattern="^(buy|sell|hold)$")
    symbol: str
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(min_length=5, max_length=500)
    position_size: int = Field(ge=0, le=10000)
    stop_loss_price: Optional[float] = Field(default=None, gt=0)
    take_profit_price: Optional[float] = Field(default=None, gt=0)

    @field_validator("symbol")
    @classmethod
    def _symbol_in_universe(cls, v: str) -> str:
        if v not in _UNIVERSE_SET:
            raise ValueError(f"universe_violation: {v} not in DJIA-30")
        return v


class DecisionRequest(BaseModel):
    idempotency_key: str = Field(min_length=1)
    actions: List[ActionItem]


# --- Submit ack ------------------------------------------------------------

class ExecutedItem(BaseModel):
    action: str
    symbol: str
    shares: float
    price: Optional[float] = None


class RejectedItem(BaseModel):
    symbol: str
    reason: str


class SubmitAck(BaseModel):
    accepted: bool
    executed: List[ExecutedItem] = Field(default_factory=list)
    rejected: List[RejectedItem] = Field(default_factory=list)
    decision_source: str  # external_agent | timeout_hold | validation_hold
    next_step: Optional[int] = None
    status: str
    run_id: str
    metrics: Optional[Dict[str, Any]] = None


# --- Result ----------------------------------------------------------------

class RunManifest(BaseModel):
    agent_name: str
    model_name: str
    mode: str
    universe: str = UNIVERSE_KEY
    start_date: str
    end_date: str
    decision_timeout_seconds: int
    schema_version: str = SCHEMA_VERSION
    news_sentiment_source: Optional[str] = None


class ResultEnvelope(BaseModel):
    run: Dict[str, Any]
    equity_curve: List[Dict[str, Any]] = Field(default_factory=list)
    trades: List[Dict[str, Any]] = Field(default_factory=list)
    decisions: List[Dict[str, Any]] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)
    manifest: Optional[RunManifest] = None


# --- Error -----------------------------------------------------------------

class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None
    retryable: bool = False


class ErrorEnvelope(BaseModel):
    error: ErrorDetail
