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

# Top 10 DJIA stocks (for 10-stock buy-and-hold mode)
TOP_10_STOCKS = ["AAPL", "MSFT", "JPM", "V", "JNJ", "WMT", "PG", "MA", "HD", "DIS"]


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
# ============================================================================
# AGENT MODE PROMPTS
# ============================================================================
BUY_AND_HOLD_PROMPT = """You are a buy-and-hold backtest agent.

Return ONLY valid JSON. No markdown. No code fences. No explanations.
Goal:
- First hour: buy 10 stocks, about $10,000 per stock.
- Later hours: hold existing positions.
- Never sell.

Rules:
1. Use only market_snapshot and VALID SYMBOLS.
2. If current_holdings is empty, generate BUY actions.
3. If current_holdings is not empty, generate HOLD actions for existing positions.
4. Do not sell.
5. Do not return all HOLD when current_holdings is empty.
6. Do not change the JSON format.

Stocks to buy on first hour:
Top 10 DJIA stocks: AAPL, MSFT, JPM, V, JNJ, WMT, PG, MA, HD, DIS

First-hour buy logic:
- allocation_per_stock = 10000 (which is 100000 / 10)
- For each stock, find its current price in market_snapshot.
- position_size = int(10000 / current_price)
- If the stock is not in VALID SYMBOLS or price is missing, skip it.
- Confidence should be 0.95.
- Reasoning should be: "Buy-and-hold initial purchase - equal 10-stock allocation."

Later-hour hold logic:
- For each of the 10 holdings, return action="hold".
- position_size must be 0.
- Confidence should be 0.90.
- Reasoning should be: "Buy-and-hold: maintain position - 10-stock portfolio."
- Generate exactly 10 HOLD actions (one per stock).

MARKET SNAPSHOT:
{market_snapshot}

VALID SYMBOLS:
{valid_symbols}

Return ONLY this JSON format:

{{
  "actions": [
    {{
      "action": "buy|sell|hold",
      "symbol": "<DJIA symbol from VALID SYMBOLS>",
      "confidence": <float 0.0-1.0>,
      "reasoning": "<short reason, max 500 chars>",
      "position_size": <integer shares, 0 for hold>,
      "stop_loss_price": <float or null>,
      "take_profit_price": <float or null>
    }}
  ]
}}

Output ONLY valid JSON.
"""

# SAFE_TRADING_PROMPT = """You are testing a BUY-AND-HOLD strategy for multiple DJIA stocks.

# === STRATEGY ===
# 1. On FIRST hour: Equally buy the top 10 DJIA stocks (by signal strength)
#    - Divide $100,000 by 10 = $10,000 per stock
#    - Buy as many shares as possible for each
# 2. On ALL other hours: HOLD (do nothing)
# 3. Never sell during the period

# === CRITICAL CONSTRAINTS ===
# 1. You CANNOT access the internet, call APIs, or use web searches
# 2. You CANNOT use tools, functions, or execute code
# 3. Your response MUST be ONLY valid JSON (no other text, no explanations)

# === RESPONSE FORMAT (JSON ONLY) ===
# {{
#   "actions": [
#     {{
#       "action": "buy|hold",
#       "symbol": "<DJIA stock>",
#       "confidence": 1.0,
#       "reasoning": "Buy and hold DJIA stocks",
#       "position_size": <integer shares, or 0 for hold>,
#       "stop_loss_price": null,
#       "take_profit_price": null
#     }},
#     ...
#   ]
# }}

# === MARKET DATA ===
# {market_snapshot}

# === INSTRUCTIONS ===
# FIRST TRADE ONLY:
# - For each of the 10 stocks in top_signals:
#   - Allocate: $100,000 / 10 = $10,000 per stock
#   - Calculate shares: floor($10,000 / stock_price)
#   - Include in actions array as BUY

# ALL OTHER TRADES:
# - For all 10 stocks: return HOLD action with position_size=0

# Respond with ONLY valid JSON."""
SAFE_TRADING_PROMPT = """You are an active DJIA portfolio trading agent.

Goal:
Trade actively enough to beat passive baselines, but avoid random trades.
Use only the provided market_snapshot. Do not use internet, tools, APIs, or code.

Output rules:
- Return ONLY valid JSON.
- No markdown.
- No code fences.
- No explanations outside JSON.
- Use only symbols from VALID SYMBOLS.
- Only sell symbols that are currently owned.
- Keep reasoning short.

Trading style:
- Prefer BUY when a stock has bullish trend or momentum.
- Prefer HOLD when signals are mixed.
- Prefer SELL only when an owned stock clearly weakens.
- Do not return all HOLD if there is cash available and at least one reasonable bullish setup.
- Do not over-focus on RSI alone.

BUY logic:
Buy when at least 2 of these are true:
- price is above SMA20
- price is above SMA50
- SMA20 is above SMA50
- MACD is above signal
- RSI is between 35 and 70
- recent return or relative strength is positive
- price is recovering from oversold conditions

Strong BUY when at least 4 of the above are true.

Avoid BUY when:
- price is below SMA50 and MACD is bearish
- RSI is above 80
- the same symbol was bought very recently
- cash is too low

SELL logic:
Only sell owned stocks.

Sell when at least 2 of these are true:
- price is below SMA20
- price is below SMA50
- MACD is below signal
- RSI is above 75 and momentum is weakening
- recent return or relative strength is poor
- the position has a meaningful unrealized loss and trend is weak

Avoid SELL when:
- the stock is still above SMA20 and SMA50
- MACD is bullish
- the only issue is high RSI in a strong uptrend

HOLD logic:
Hold when:
- signals are mixed
- the stock is already owned and trend is still acceptable
- cash is limited
- recent_trades show the symbol was traded too recently

Activity rule:
- If cash is available and the portfolio has fewer than 8 holdings, prefer 2 to 5 BUY actions.
- If the portfolio already has many holdings, prefer holding winners and selling weak positions.
- Do not output more than 8 actions total.
- Prioritize the best opportunities from top_signals and current_holdings.

Position sizing:
- Medium BUY: use about 5% of portfolio value.
- Strong BUY: use about 8% to 10% of portfolio value.
- Never use more than 12% of portfolio value on one new stock.
- position_size must be an integer share count.
- If price or cash is missing, use position_size 1 for BUY.
- For HOLD, position_size must be 0.
- For SELL, position_size should be the shares to sell if available; otherwise use 1.

Confidence:
- BUY confidence should usually be 0.65 to 0.90.
- SELL confidence should usually be 0.65 to 0.90.
- HOLD confidence should usually be 0.30 to 0.60.
- Use confidence above 0.85 only for very clear setups.

MARKET SNAPSHOT:
{market_snapshot}

VALID SYMBOLS:
{valid_symbols}

Return exactly this JSON shape:

{{
  "actions": [
    {{
      "action": "buy|sell|hold",
      "symbol": "<DJIA symbol>",
      "confidence": 0.75,
      "reasoning": "<short reason using trend, momentum, RSI, or risk>",
      "position_size": 1,
      "stop_loss_price": null,
      "take_profit_price": null
    }}
  ]
}}

Return ONLY valid JSON.
"""


def create_safe_prompt(market_snapshot: Dict[str, Any]) -> str:
    """Create a safe prompt for LLM trading decision."""
    return SAFE_TRADING_PROMPT.format(
        market_snapshot=json.dumps(market_snapshot, indent=2),
        valid_symbols=", ".join(DJIA_30)
    )


def create_prompt(market_snapshot: Dict[str, Any], mode: str = "safe_trading") -> str:
    """
    Create a prompt for LLM trading decision based on mode.
    
    Args:
        market_snapshot: Market data snapshot
        mode: "safe_trading" or "buy_and_hold"
    
    Returns:
        Formatted prompt string
    """
    if mode == "buy_and_hold":
        return BUY_AND_HOLD_PROMPT.format(
            market_snapshot=json.dumps(market_snapshot, indent=2),
            valid_symbols=", ".join(DJIA_30)
        )
    else:
        return create_safe_prompt(market_snapshot)
