"""
LLM Trading Decision Validator

Provides strict validation for LLM trading responses:
- Enforces JSON-only responses (no tool_calls)
- Validates against trading schema
- Checks portfolio constraints
- Logs all decisions for audit trail

Usage:
    decision = validate_llm_response(raw_response, portfolio_state)
"""

import json
import logging
from typing import Dict, Any, Optional
from enum import Enum
from decimal import Decimal
from datetime import datetime
from pydantic import BaseModel, field_validator, ValidationError, ConfigDict

logger = logging.getLogger(__name__)

# DJIA 30 stocks (must match backtest_hourly_agent.py)
DJIA_30 = [
    "AAPL", "MSFT", "JPM", "V", "JNJ",
    "WMT", "PG", "MA", "HD", "DIS",
    "MCD", "PFE", "CSCO", "IBM", "INTC",
    "XOM", "AXP", "KO", "CAT", "GS",
    "MRK", "NVDA", "BA", "UNH", "MMM",
    "CVX", "NKE", "AMEX", "TRV", "WBA"
]


class TradingAction(str, Enum):
    """Allowed trading actions"""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class LLMTradingDecision(BaseModel):
    """
    Strict schema for LLM trading responses.
    
    The LLM MUST respond with JSON matching this schema.
    Any attempt to call tools or functions will be rejected.
    """
    model_config = ConfigDict(use_enum_values=True)
    
    action: TradingAction
    symbol: str
    confidence: float
    reasoning: str
    position_size: int
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    
    @field_validator('symbol')
    @classmethod
    def validate_symbol(cls, v):
        """Ensure symbol is in DJIA 30"""
        if v not in DJIA_30:
            raise ValueError(f"Invalid symbol: {v}. Must be one of {DJIA_30}")
        return v
    
    @field_validator('confidence')
    @classmethod
    def validate_confidence(cls, v):
        """Confidence must be 0.0 to 1.0"""
        if not isinstance(v, (int, float)):
            raise ValueError(f"Confidence must be numeric, got {type(v)}")
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"Confidence {v} out of range [0.0, 1.0]")
        return float(v)
    
    @field_validator('reasoning')
    @classmethod
    def validate_reasoning(cls, v):
        """Reasoning must be string, max 500 chars"""
        if not isinstance(v, str):
            raise ValueError(f"Reasoning must be string, got {type(v)}")
        if len(v) > 500:
            raise ValueError(f"Reasoning too long: {len(v)} > 500 chars")
        if len(v) < 5:
            raise ValueError(f"Reasoning too short: {len(v)} < 5 chars")
        return v
    
    @field_validator('position_size')
    @classmethod
    def validate_position_size(cls, v):
        """Position size must be non-negative integer"""
        if not isinstance(v, int):
            raise ValueError(f"Position size must be integer, got {type(v)}")
        if v < 0:
            raise ValueError(f"Position size cannot be negative: {v}")
        if v > 10000:  # Reasonable max: no single position > 10k shares
            raise ValueError(f"Position size too large: {v} > 10000")
        return v
    
    @field_validator('stop_loss_price', mode='before')
    @classmethod
    def validate_stop_loss(cls, v):
        """Stop loss must be valid and positive"""
        if v is None:
            return v
        if not isinstance(v, (int, float)):
            raise ValueError(f"Stop loss must be numeric, got {type(v)}")
        if v <= 0:
            raise ValueError(f"Stop loss must be positive: {v}")
        return float(v)
    
    @field_validator('take_profit_price', mode='before')
    @classmethod
    def validate_take_profit(cls, v):
        """Take profit must be valid and positive"""
        if v is None:
            return v
        if not isinstance(v, (int, float)):
            raise ValueError(f"Take profit must be numeric, got {type(v)}")
        if v <= 0:
            raise ValueError(f"Take profit must be positive: {v}")
        return float(v)


class PortfolioConstraints(BaseModel):
    """Portfolio constraints to validate against"""
    cash_available: float
    max_position_size: int = 5000
    max_daily_trades: int = 20
    max_position_value: float = 50000
    min_confidence: float = 0.3  # Don't execute low-confidence decisions


def validate_llm_response(
    raw_response: str,
    portfolio_state: Dict[str, Any],
    current_prices: Dict[str, float]
) -> Optional[LLMTradingDecision]:
    """
    Validate LLM response and check portfolio constraints.
    
    Args:
        raw_response: Raw string from LLM
        portfolio_state: Current portfolio state
        current_prices: Current market prices {symbol: price}
    
    Returns:
        LLMTradingDecision if valid, None if invalid (reason logged)
    
    Raises:
        ValidationError: If response is malformed
    """
    
    # =========================================================================
    # CRITICAL CHECK 1: Reject tool_calls or function_calls
    # =========================================================================
    if "tool_use" in raw_response or "tool_calls" in raw_response or \
       "function_calls" in raw_response or "invoke" in raw_response:
        logger.error(
            "🚨 SECURITY: LLM attempted tool calling! Rejecting response entirely.",
            extra={"raw_response_preview": raw_response[:200]}
        )
        return None
    
    # =========================================================================
    # CRITICAL CHECK 2: Parse JSON
    # =========================================================================
    try:
        json_data = json.loads(raw_response)
    except json.JSONDecodeError as e:
        logger.warning(
            f"❌ Invalid JSON from LLM: {e}",
            extra={"raw_response_preview": raw_response[:200]}
        )
        return None
    
    # =========================================================================
    # CRITICAL CHECK 3: Schema validation
    # =========================================================================
    try:
        decision = LLMTradingDecision(**json_data)
    except ValidationError as e:
        logger.warning(
            f"❌ Schema validation failed: {e}",
            extra={"errors": e.errors(), "json_data": json_data}
        )
        return None
    
    # =========================================================================
    # CHECK 4: Portfolio constraints
    # =========================================================================
    constraints = PortfolioConstraints(**portfolio_state.get("constraints", {}))
    
    # Check confidence threshold
    if decision.confidence < constraints.min_confidence:
        logger.info(
            f"⏭️ Decision confidence {decision.confidence} below minimum {constraints.min_confidence}. "
            f"Treating as HOLD.",
            extra={"decision": decision.model_dump()}
        )
        decision.action = TradingAction.HOLD
        decision.position_size = 0
        return decision
    
    # Check cash availability for BUY
    if decision.action == TradingAction.BUY:
        current_price = current_prices.get(decision.symbol, 0)
        total_cost = decision.position_size * current_price
        
        if total_cost > constraints.cash_available:
            logger.warning(
                f"❌ BUY {decision.symbol}: Insufficient cash. "
                f"Need ${total_cost:,.2f}, have ${constraints.cash_available:,.2f}",
                extra={"decision": decision.model_dump(), "cost": total_cost}
            )
            return None
        
        if decision.position_size > constraints.max_position_size:
            logger.warning(
                f"❌ BUY {decision.symbol}: Position size {decision.position_size} "
                f"exceeds max {constraints.max_position_size}",
                extra={"decision": decision.model_dump()}
            )
            return None
        
        if total_cost > constraints.max_position_value:
            logger.warning(
                f"❌ BUY {decision.symbol}: Position value ${total_cost:,.2f} "
                f"exceeds max ${constraints.max_position_value:,.2f}",
                extra={"decision": decision.model_dump()}
            )
            return None
    
    # Check that SELL has valid position
    if decision.action == TradingAction.SELL:
        positions = {p["symbol"]: p["shares"] for p in portfolio_state.get("positions", [])}
        if decision.symbol not in positions:
            logger.warning(
                f"❌ SELL {decision.symbol}: No position to sell",
                extra={"decision": decision.model_dump(), "positions": positions}
            )
            return None
        
        if decision.position_size > positions[decision.symbol]:
            logger.warning(
                f"❌ SELL {decision.symbol}: Trying to sell {decision.position_size} "
                f"shares, only have {positions[decision.symbol]}",
                extra={"decision": decision.model_dump()}
            )
            return None
    
    logger.info(
        f"✅ LLM decision validated: {decision.action.upper()} {decision.symbol} "
        f"{decision.position_size} @ confidence {decision.confidence:.0%}",
        extra={"decision": decision.model_dump()}
    )
    
    return decision


def log_audit_trail(
    session_id: str,
    decision: LLMTradingDecision,
    llm_raw_response: str,
    execution_status: str,
    error_msg: Optional[str] = None
):
    """
    Log LLM decision to audit trail for compliance and debugging.
    
    Args:
        session_id: User session ID
        decision: Validated trading decision
        llm_raw_response: Raw response from LLM
        execution_status: "success", "rejected", "failed"
        error_msg: Optional error message
    """
    audit_record = {
        "timestamp": datetime.utcnow().isoformat(),
        "session_id": session_id,
        "decision": decision.model_dump() if decision else None,
        "execution_status": execution_status,
        "error": error_msg,
        "llm_response_preview": llm_raw_response[:300]
    }
    
    logger.info(
        f"📋 AUDIT: {execution_status.upper()} decision for session {session_id[:8]}",
        extra=audit_record
    )


# ============================================================================
# Safe Prompt Template (for integration)
# ============================================================================

SAFE_TRADING_PROMPT = """You are a trading decision advisor for a portfolio of DJIA stocks.

CRITICAL CONSTRAINTS (non-negotiable):
1. You CANNOT access the internet, call APIs, or use web searches
2. You CANNOT use tools, functions, or execute code
3. Your response MUST be ONLY valid JSON (no other text, no explanations)
4. You CANNOT attempt tool_use, function_calls, or any API access
5. If unsure, respond with: {{"action": "hold"}}

MARKET DATA (read-only):
{market_snapshot}

VALID SYMBOLS: {valid_symbols}

RESPONSE SCHEMA (JSON only):
{{
  "action": "buy|sell|hold",
  "symbol": "<DJIA symbol>",
  "confidence": <0.0-1.0>,
  "reasoning": "<max 500 chars>",
  "position_size": <integer>,
  "stop_loss_price": <optional float>,
  "take_profit_price": <optional float>
}}

Respond with ONLY the JSON object. Nothing else. No markdown, no explanations."""


def create_safe_prompt(market_snapshot: Dict[str, Any]) -> str:
    """Create a safe prompt for LLM trading decision."""
    return SAFE_TRADING_PROMPT.format(
        market_snapshot=json.dumps(market_snapshot, indent=2),
        valid_symbols=", ".join(DJIA_30)
    )
