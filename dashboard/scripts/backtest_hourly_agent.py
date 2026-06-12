#!/usr/bin/env python3
"""
Hourly DJIA Backtest with Agent Decision Making

The agent manages a $100k portfolio across DJIA stocks.
Each hour, the agent analyzes market data and technical indicators and decides:
- What positions to buy
- What positions to sell  
- What positions to hold

This generates a realistic equity curve based on agent decision-making.

Uses REAL Alpaca hourly data with forward-filled price cache for missing bars.

Usage:
    python3 backtest_hourly_agent.py --start 2026-03-01 --end 2026-04-23
"""

import sys
import json
import argparse
import os
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import uuid
import numpy as np
import pandas as pd
import requests

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from paths import CREDENTIALS_DIR
from database import db
from baseline_generator import generate_baselines
from llm_validator import create_safe_prompt, create_prompt, validate_llm_response, LLMTradingDecision, TOP_10_STOCKS

# Optional: LLM integration
try:
    from anthropic import Anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False
    print("⚠️  Anthropic SDK not installed. Fallback to rule-based trading.")
    print("   To enable LLM: pip install anthropic")

try:
    import pandas_ta as ta
except ImportError:
    print("Installing pandas_ta...")
    import subprocess
    subprocess.check_call(["pip", "install", "pandas_ta"])
    import pandas_ta as ta

# ============================================================================
# DJIA 30 Stocks
# ============================================================================

DJIA_30 = [
    "AAPL", "MSFT", "JPM", "V", "JNJ",
    "WMT", "PG", "MA", "HD", "DIS",
    "MCD", "PFE", "CSCO", "IBM", "INTC",
    "XOM", "AXP", "KO", "CAT", "GS",
    "MRK", "NVDA", "BA", "UNH", "MMM",
    "CVX", "NKE", "AMEX", "TRV", "WBA"
]

# Top 10 DJIA stocks (for buy-and-hold and baseline)
TOP_10 = TOP_10_STOCKS  # Import from llm_validator to keep them in sync

# ============================================================================
# JSON Parsing Utilities
# ============================================================================

def fix_json_formatting(json_str: str) -> str:
    """
    Try to fix common JSON formatting issues from LLM responses.
    
    Fixes:
    - Missing commas between objects in arrays
    - Trailing commas
    - Extra closing brackets
    """
    # Fix 1: Add missing commas between objects in arrays (most common issue)
    # Pattern: } followed by newline(s) and whitespace and {  
    # This handles: }
    #             {
    json_str = re.sub(r'(\})\s*\n\s*(\{)', r'\1,\n\2', json_str)
    
    # Fix 1b: Also handle } with no space then {
    json_str = re.sub(r'(\})(\{)', r'\1,\2', json_str)
    
    # Fix 2: Remove trailing commas before closing brackets
    # Pattern: , followed by optional whitespace and ] or }
    json_str = re.sub(r',(\s*[\]}])', r'\1', json_str)
    
    # Fix 3: Remove multiple closing brackets (sometimes LLM adds extra ones)
    # Pattern: ]]}  should be ]
    json_str = re.sub(r'\]\s*\}\s*\]', ']', json_str)
    
    # Fix 4: Fix }] at the end - should just be ]
    json_str = re.sub(r'\}\s*\]\s*$', ']', json_str)
    
    return json_str


# ============================================================================
# LLM Model Configuration
# ============================================================================

LLM_MODEL_NAME = "claude-haiku-4-5-20251001"  # Change this to switch models

# ============================================================================
# Configuration
# ============================================================================

DEFAULT_START = "2026-03-01"
DEFAULT_END = "2026-04-13"
INITIAL_CAPITAL = 100000
TIMEFRAME = "1h"  # Hourly


# ============================================================================
# Data Loader - Alpaca API
# ============================================================================

class AlpacaDataLoader:
    """Fetches historical hourly bars from Alpaca API."""
    
    def __init__(self, api_key: Optional[str] = None, secret_key: Optional[str] = None):
        """Initialize with Alpaca credentials."""
        if not api_key or not secret_key:
            creds = self._load_credentials()
            api_key = creds.get("api_key")
            secret_key = creds.get("secret_key")
        
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = "https://data.alpaca.markets"
        
        try:
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.data.requests import StockBarsRequest
            from alpaca.data.timeframe import TimeFrame
            
            self.client = StockHistoricalDataClient(self.api_key, self.secret_key)
            self.StockBarsRequest = StockBarsRequest
            self.TimeFrame = TimeFrame
            print("✅ Alpaca credentials loaded")
        except ImportError as e:
            print(f"❌ alpaca-py not installed: {e}")
            print("   Run: pip install alpaca-py")
            sys.exit(1)
    
    def _load_credentials(self) -> Dict:
        """Load Alpaca credentials from environment variables or file."""
        # Try environment variables first (for Render, Docker, etc.)
        api_key = os.getenv('ALPACA_API_KEY')
        secret_key = os.getenv('ALPACA_SECRET_KEY')
        
        if api_key and secret_key:
            print("✅ Loaded Alpaca credentials from environment variables")
            return {"api_key": api_key, "secret_key": secret_key}
        
        # Fall back to credentials file (for local development)
        creds_path = CREDENTIALS_DIR / "alpaca.json"
        if not creds_path.exists():
            print(f"❌ Credentials not found in environment variables or file: {creds_path}")
            print("   Set ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables")
            sys.exit(1)
        
        print(f"✅ Loaded Alpaca credentials from {creds_path}")
        with open(creds_path) as f:
            return json.load(f)
    
    def fetch_bars(self, symbols: List[str], start: str, end: str) -> Dict[str, pd.DataFrame]:
        """
        Fetch hourly OHLCV data from Alpaca API.
        
        Args:
            symbols: List of stock symbols
            start: Start date (YYYY-MM-DD)
            end: End date (YYYY-MM-DD)
        
        Returns:
            {symbol: DataFrame with timestamp, open, high, low, close, volume}
        """
        print(f"\n📊 Fetching {len(symbols)} symbols from {start} to {end}...")
        print(f"   Timeframe: Hourly (1h) with forward-filled price cache\n")
        
        request = self.StockBarsRequest(
            symbol_or_symbols=symbols,
            timeframe=self.TimeFrame.Hour,
            start=start,
            end=end,
        )
        
        try:
            bars = self.client.get_stock_bars(request)
            
            # Convert to DataFrame per symbol
            data = {}
            for symbol in symbols:
                if symbol in bars.df.index.get_level_values(0):
                    df = bars.df.xs(symbol).reset_index()
                    
                    # Extract OHLCV columns
                    df = df[["timestamp", "open", "high", "low", "close", "volume"]].copy()
                    df["timestamp"] = pd.to_datetime(df["timestamp"])
                    df.set_index("timestamp", inplace=True)
                    data[symbol] = df.sort_index()
                    print(f"  ✅ {symbol}: {len(df)} hourly bars")
                else:
                    print(f"  ⚠️  {symbol}: No data available")
            
            return data
        
        except Exception as e:
            print(f"❌ Error fetching bars: {e}")
            import traceback
            traceback.print_exc()
            return {}


# ============================================================================
# Technical Indicators
# ============================================================================

class TechnicalIndicators:
    """Calculates technical indicators for trading signals."""
    
    @staticmethod
    def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate technical indicators.
        
        Indicators:
        - RSI (14-period)
        - MACD (12/26/9)
        - Bollinger Bands (20/2)
        - SMA (20 & 50-period)
        
        IMPORTANT: Requires minimum 50 bars for reliable signals.
        Backtests shorter than 1 month will have unreliable indicators.
        """
        if df is None or df.empty:
            print(f"Warning: Empty or None dataframe, skipping indicators")
            return df
        
        df = df.copy()
        
        # Check if we have enough data for indicators
        min_required = 50  # Need at least 50 bars for SMA50
        if len(df) < min_required:
            print(f"\n⚠️  DATA WARNING: Only {len(df)} bars, need {min_required}!")
            print(f"   Indicators will be unreliable. Backtest needs at least 1 month of data.")
            print(f"   Recommended: 3+ months for meaningful results.\n")
            # Still calculate what we can
        
        try:
            # RSI (14-period requires 14+ bars)
            if len(df) >= 14:
                rsi = ta.rsi(df["close"], length=14)
                if rsi is not None:
                    df["rsi_14"] = rsi
                else:
                    df["rsi_14"] = 50.0  # Default neutral RSI
            else:
                df["rsi_14"] = 50.0  # Not enough data
            
            # MACD (26-period required)
            if len(df) >= 26:
                macd = ta.macd(df["close"], fast=12, slow=26, signal=9)
                if macd is not None and isinstance(macd, pd.DataFrame):
                    macd_cols = [c for c in macd.columns if "MACD_12_26_9" in c]
                    signal_cols = [c for c in macd.columns if "MACDs_12_26_9" in c]
                    if macd_cols:
                        df["macd"] = macd[macd_cols[0]]
                    else:
                        df["macd"] = 0.0
                    if signal_cols:
                        df["macd_signal"] = macd[signal_cols[0]]
                    else:
                        df["macd_signal"] = 0.0
                else:
                    df["macd"] = 0.0
                    df["macd_signal"] = 0.0
            else:
                df["macd"] = 0.0
                df["macd_signal"] = 0.0
            
            # Bollinger Bands (20-period required)
            if len(df) >= 20:
                bbands = ta.bbands(df["close"], length=20, std=2)
                if bbands is not None and isinstance(bbands, pd.DataFrame):
                    bbu_cols = [c for c in bbands.columns if "BBU" in c]
                    bbl_cols = [c for c in bbands.columns if "BBL" in c]
                    if bbu_cols:
                        df["bb_upper"] = bbands[bbu_cols[0]]
                    else:
                        df["bb_upper"] = df["close"].max()
                    if bbl_cols:
                        df["bb_lower"] = bbands[bbl_cols[0]]
                    else:
                        df["bb_lower"] = df["close"].min()
                else:
                    df["bb_upper"] = df["close"].max()
                    df["bb_lower"] = df["close"].min()
            else:
                df["bb_upper"] = df["close"].max()
                df["bb_lower"] = df["close"].min()
            
            # SMAs
            if len(df) >= 20:
                sma20 = ta.sma(df["close"], length=20)
                df["sma20"] = sma20 if sma20 is not None else df["close"].mean()
            else:
                df["sma20"] = df["close"].mean()
            
            if len(df) >= 50:
                sma50 = ta.sma(df["close"], length=50)
                df["sma50"] = sma50 if sma50 is not None else df["close"].mean()
            else:
                df["sma50"] = df["close"].mean()
            
        except Exception as e:
            print(f"Warning: Error calculating indicators: {e}")
            # Fill in defaults
            for col in ["rsi_14", "macd", "macd_signal", "bb_upper", "bb_lower", "sma20", "sma50"]:
                if col not in df.columns:
                    df[col] = df["close"].mean() if col != "rsi_14" else 50.0
        
        return df


# ============================================================================
# Portfolio Manager with Agent Decision Logic
# ============================================================================

class PortfolioManager:
    """Manages portfolio with hourly trading decisions based on indicators."""
    
    def __init__(self, initial_capital: float = 100000):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions = {}  # {symbol: num_shares}
        self.entry_prices = {}  # {symbol: entry_price}
        self.trades = []
        self.equity_history = []
    
    def get_portfolio_state(self, market_data: Dict[str, pd.Series], price_cache: Dict = None, timestamp = None) -> Dict:
        """Get current portfolio state with market indicators.
        
        Uses real data for signals, forward-filled prices for valuation.
        """
        positions_value = 0
        position_list = []
        
        for symbol, shares in self.positions.items():
            # Get current price (prefer real data, fallback to cache)
            if symbol in market_data:
                current_price = market_data[symbol]["close"]
            elif price_cache and symbol in price_cache and timestamp in price_cache[symbol]:
                current_price = price_cache[symbol][timestamp]
            else:
                continue  # Skip if no price available
            
            position_value = shares * current_price
            positions_value += position_value
            entry_price = self.entry_prices.get(symbol, current_price)
            pnl_pct = ((current_price / entry_price) - 1) * 100 if entry_price > 0 else 0
            
            position_list.append({
                "symbol": symbol,
                "shares": shares,
                "entry_price": entry_price,
                "current_price": current_price,
                "position_value": position_value,
                "pnl_pct": pnl_pct
            })
        
        # Get signals for all stocks (only from real data)
        market_signals = {}
        for symbol, row in market_data.items():
            market_signals[symbol] = {
                "price": row["close"],
                "rsi": row.get("rsi_14"),
                "macd": row.get("macd"),
                "macd_signal": row.get("macd_signal"),
                "sma20": row.get("sma20"),
                "sma50": row.get("sma50"),
                "bb_upper": row.get("bb_upper"),
                "bb_lower": row.get("bb_lower"),
            }
        
        return {
            "cash": self.cash,
            "positions": position_list,
            "positions_value": positions_value,
            "total_equity": self.cash + positions_value,
            "market_signals": market_signals,
        }
    
    def make_trading_decision(self, portfolio_state: Dict) -> Dict:
        """
        Agent makes trading decisions based on technical indicators.
        
        Rules:
        - BUY: RSI < 30 AND Price < SMA20 (oversold + downtrend)
        - SELL: RSI > 70 OR Price > SMA50 + 2% (overbought)
        - HOLD: Otherwise
        
        Returns:
            {"actions": [{"symbol": "AAPL", "action": "buy", "shares": 10}, ...]}
        """
        actions = []
        
        # Calculate total portfolio equity for consistent position sizing
        total_equity = portfolio_state["total_equity"]
        
        for symbol, signal in portfolio_state["market_signals"].items():
            rsi = signal.get("rsi")
            price = signal.get("price")
            sma20 = signal.get("sma20")
            sma50 = signal.get("sma50")
            
            # Skip if indicators not ready
            if pd.isna([rsi, sma20]).any():
                continue
            
            has_position = symbol in self.positions and self.positions[symbol] > 0
            
            # BUY logic: RSI < 30 (oversold)
            if not has_position and rsi < 30 and price < sma20:
                # Size: 2% of TOTAL PORTFOLIO per trade (not just cash)
                risk_amount = total_equity * 0.02
                shares_to_buy = int(risk_amount / price)
                if shares_to_buy > 0 and shares_to_buy * price <= self.cash:
                    actions.append({
                        "symbol": symbol,
                        "action": "buy",
                        "shares": shares_to_buy,
                        "reason": f"RSI oversold ({rsi:.0f}), price below MA"
                    })
            
            # SELL logic: RSI > 70 (overbought) or price above SMA50
            elif has_position and (rsi > 70 or (sma50 and price > sma50 * 1.02)):
                actions.append({
                    "symbol": symbol,
                    "action": "sell",
                    "shares": self.positions[symbol],
                    "reason": f"RSI overbought ({rsi:.0f})" if rsi > 70 else "Price above MA50"
                })
        
        return {"actions": actions}
    
    def make_trading_decision_with_llm(self, portfolio_state: Dict, llm_client, mode: str = "safe_trading") -> Dict:
        """
        Make trading decisions using Claude LLM with technical indicators.
        
        The LLM receives:
        - All technical indicators (RSI, MACD, Bollinger Bands, SMAs)
        - Current portfolio state
        - Recent trade history (last 24 hours) for context and memory
        - Clear instructions on how to interpret signals
        
        Args:
            portfolio_state: Current portfolio state with market signals
            llm_client: Anthropic client instance
            mode: "safe_trading" (risk management) or "buy_and_hold" (debug mode)
        
        Returns:
            {"actions": [list of trading actions]}
        """
        if not HAS_ANTHROPIC or not llm_client:
            print("\u26a0️  LLM client not available, using rule-based fallback")
            return self.make_trading_decision(portfolio_state)
        
        try:
            # ================================================================
            # STEP 1: Create prompt with all technical indicators
            # ================================================================
            # Convert timestamp to ISO format string (handle pandas Timestamp)
            timestamp = portfolio_state.get("timestamp", datetime.now())
            if hasattr(timestamp, 'isoformat'):
                timestamp_str = timestamp.isoformat()
            else:
                timestamp_str = str(timestamp)
            
            # Extract current holdings for LLM decision-making
            holdings = {}
            for position in portfolio_state["positions"]:
                holdings[position["symbol"]] = {
                    "shares": position["shares"],
                    "entry_price": round(position["entry_price"], 2),
                    "current_price": round(position["current_price"], 2),
                    "position_value": round(position["position_value"], 2),
                    "pnl_pct": round(position["pnl_pct"], 2)
                }
            
            # Extract recent trade history (last 24 hours) for LLM memory
            # This prevents LLM from re-entering stocks too soon
            recent_trades = []
            cutoff_time = timestamp - timedelta(hours=24)
            for trade in self.trades:
                if trade["timestamp"] > cutoff_time:
                    recent_trades.append({
                        "symbol": trade["symbol"],
                        "side": trade["side"],
                        "shares": trade["shares"],
                        "price": round(float(trade["price"]), 2),
                        "timestamp": trade["timestamp"].isoformat() if hasattr(trade["timestamp"], 'isoformat') else str(trade["timestamp"])
                    })
            
            market_snapshot = {
                "timestamp": timestamp_str,
                "portfolio": {
                    "cash": round(portfolio_state["cash"], 2),
                    "positions_value": round(portfolio_state["positions_value"], 2),
                    "total_equity": round(portfolio_state["total_equity"], 2),
                    "num_positions": len(portfolio_state["positions"])
                },
                "current_holdings": holdings,  # What we currently own
                "recent_trades": recent_trades,  # Last 24h of trades (memory)
                "top_signals": {}
            }
            
            # Add market signals to snapshot
            signals = portfolio_state["market_signals"]
            
            # For buy-and-hold mode, use ALL 30 DJIA stocks (match baseline)
            if mode == "buy_and_hold":
                # Use all DJIA 30 stocks (same as baseline)
                symbols_to_include = [s for s in DJIA_30 if s in signals]
            else:
                # For safe_trading, use RSI extremes (most tradeable opportunities)
                rsi_sorted = sorted(
                    [(sym, sig.get("rsi", 50)) for sym, sig in signals.items()],
                    key=lambda x: abs(x[1] - 50),  # Distance from neutral
                    reverse=True
                )
                symbols_to_include = [sym for sym, _ in rsi_sorted[:10]]
            
            for symbol in symbols_to_include:
                signal = signals[symbol]
                
                # Extract values, allowing zero values (they're still valid prices)
                rsi = float(signal.get("rsi", 50)) if pd.notna(signal.get("rsi")) else 50.0
                macd = float(signal.get("macd", 0)) if pd.notna(signal.get("macd")) else 0.0
                macd_sig = float(signal.get("macd_signal", 0)) if pd.notna(signal.get("macd_signal")) else 0.0
                sma20 = float(signal.get("sma20", 0)) if pd.notna(signal.get("sma20")) else 0.0
                sma50 = float(signal.get("sma50", 0)) if pd.notna(signal.get("sma50")) else 0.0
                bb_upper = float(signal.get("bb_upper", 0)) if pd.notna(signal.get("bb_upper")) else 0.0
                bb_lower = float(signal.get("bb_lower", 0)) if pd.notna(signal.get("bb_lower")) else 0.0
                price = float(signal.get("price", 0)) if pd.notna(signal.get("price")) else 0.0
                
                # Always include these stocks with their price (critical for LLM calculation)
                market_snapshot["top_signals"][symbol] = {
                    "price": price,
                    "rsi": rsi,
                    "macd": macd,
                    "macd_signal": macd_sig,
                    "sma20": sma20,
                    "sma50": sma50,
                    "bb_upper": bb_upper,
                    "bb_lower": bb_lower,
                }
            
            # Ensure market_snapshot is fully JSON-serializable before sending
            try:
                json.dumps(market_snapshot)  # Verify it's serializable
            except TypeError as e:
                print(f"   ⚠️  Market snapshot serialization error: {e}")
                print(f"   Falling back to rule-based logic")
                return self.make_trading_decision(portfolio_state)
            
            # DEBUG: Show what's in market_snapshot for buy-and-hold mode
            if mode == "buy_and_hold" and not self.positions:
                print(f"\n   DEBUG market_snapshot:")
                print(f"     Cash: ${market_snapshot['portfolio']['cash']}")
                print(f"     Top signals count: {len(market_snapshot['top_signals'])}")
                if market_snapshot['top_signals']:
                    for symbol, signal in list(market_snapshot['top_signals'].items())[:3]:
                        print(f"       {symbol}: price=${signal.get('price', 'MISSING')}")
                print()
            
            prompt = create_prompt(market_snapshot, mode=mode)
            
            print(f"\n🤖 Calling LLM for trading decision...")
            print(f"   Signals analyzed: {len(market_snapshot['top_signals'])} stocks")
            print(f"   Portfolio: Cash=${market_snapshot['portfolio']['cash']:.0f}, Equity=${market_snapshot['portfolio']['total_equity']:.0f}")
            print(f"   Top signals:")
            for symbol, signal in list(market_snapshot['top_signals'].items())[:3]:
                rsi = signal.get('rsi', 50)
                price = signal.get('price', 0)
                print(f"      {symbol}: ${price:.2f} (RSI={rsi:.1f})")
            
            # ================================================================
            # STEP 2: Call Claude with technical indicator analysis
            # ================================================================
            response = llm_client.messages.create(
                model=LLM_MODEL_NAME,
                max_tokens=2000,  # Reduced from 3000 (saves tokens)
                system="""You are an expert quantitative trading advisor analyzing DJIA stocks.

You have deep knowledge of:
- Technical analysis (RSI, MACD, Bollinger Bands, Moving Averages)
- Indicator interpretation and confluence
- Risk management and position sizing
- Trading psychology and market microstructure

IMPORTANT INSTRUCTIONS:
1. Analyze EACH stock signal provided (don't skip any)
2. For each stock, decide: BUY, SELL, or HOLD
3. Always include a confidence score (0.0-1.0)
4. Return a JSON object with an "actions" array containing one entry per stock
5. Even if you decide HOLD, include it in the actions array
6. Respond with ONLY valid JSON - no explanations outside JSON

Make precise, actionable trading decisions based on the technical indicators provided.""",
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            llm_response = response.content[0].text
            
            # ================================================================
            # STEP 3: Parse and validate LLM response
            # ================================================================
            print(f"\n📫 Parsing LLM response...")
            print(f"   Raw response (first 300 chars): {llm_response[:300]}")
            
            try:
                # Extract JSON from response
                # First, strip markdown code fences if present
                response_cleaned = llm_response
                if '```json' in response_cleaned:
                    response_cleaned = response_cleaned.replace('```json', '').replace('```', '')
                elif '```' in response_cleaned:
                    response_cleaned = response_cleaned.replace('```', '')
                
                start = response_cleaned.find('{')
                end = response_cleaned.rfind('}') + 1
                if start < 0 or end <= 0:
                    print(f"   ❌ No JSON found in response")
                    print(f"   Full response: {response_cleaned[:500]}")
                    return {"actions": []}
                
                json_str = response_cleaned[start:end]
                
                # Try to parse
                try:
                    decision = json.loads(json_str)
                    print(f"   ✅ JSON parsed successfully")
                except json.JSONDecodeError as e:
                    # Try to fix common formatting issues
                    print(f"   ⚠️  Initial parse failed: {e}")
                    print(f"   Attempting to fix JSON formatting...")
                    
                    json_str_fixed = fix_json_formatting(json_str)
                    try:
                        decision = json.loads(json_str_fixed)
                        print(f"   ✅ JSON fixed and parsed successfully!")
                    except json.JSONDecodeError as e2:
                        print(f"   ❌ Still failed after fix: {e2}")
                        print(f"   Error at line {e2.lineno}, column {e2.colno}")
                        
                        # Show detailed context around error
                        lines = json_str_fixed.split('\n')
                        if e2.lineno <= len(lines):
                            start = max(0, e2.lineno - 3)
                            end = min(len(lines), e2.lineno + 2)
                            print(f"\n   Context around error (lines {start+1}-{end}):")
                            for i in range(start, end):
                                marker = ">> " if i == e2.lineno - 1 else "   "
                                print(f"   {marker}{i+1:3d}: {lines[i][:70]}")
                        
                        # Try one more aggressive fix
                        print(f"\n   Attempting second fix attempt (validate structure)...")
                        try:
                            # Count opening vs closing brackets
                            open_count = json_str_fixed.count('{')
                            close_count = json_str_fixed.count('}')
                            if open_count != close_count:
                                print(f"   Bracket mismatch: {open_count} open, {close_count} close")
                                # Remove extra closing brackets from the end
                                while json_str_fixed.count('}') > json_str_fixed.count('{'):
                                    json_str_fixed = json_str_fixed.rsplit('}', 1)[0] + '}'
                                print(f"   Removed extra closing brackets")
                            
                            decision = json.loads(json_str_fixed)
                            print(f"   ✅ JSON fixed after structure cleanup!")
                        except json.JSONDecodeError as e3:
                            print(f"   ❌ Cannot fix: {e3}")
                            return {"actions": []}
                
                print(f"   Actions from LLM: {len(decision.get('actions', []))}")
                
            except (json.JSONDecodeError, ValueError, Exception) as e:
                print(f"   ❌ Failed to parse JSON: {e}")
                print(f"   LLM response: {llm_response[:500]}...")
                return {"actions": []}
            
            # ================================================================
            # STEP 4: Convert LLM decisions to actions
            # ================================================================
            actions = []
            llm_actions = decision.get("actions", [])
            
            if not llm_actions:
                print(f"   ⚠️  LLM returned no actions. Decision object: {decision}")
                print(f"   Falling back to rule-based logic")
                return self.make_trading_decision(portfolio_state)
            
            for llm_action in llm_actions:
                symbol = llm_action.get("symbol")
                action_type = llm_action.get("action", "hold").lower()
                confidence = llm_action.get("confidence", 0.5)
                reasoning = llm_action.get("reasoning", "")
                
                print(f"\n   Processing: {symbol} ({action_type.upper()}, conf={confidence:.0%})")
                print(f"      Reasoning: {reasoning[:60]}...")
                
                # Skip low-confidence decisions
                if confidence < 0.3:
                    print(f"      ⏸️  Skipping (confidence {confidence:.0%} too low)")
                    continue
                
                if symbol not in DJIA_30:
                    print(f"   ❌ {symbol}: Invalid symbol, skipping")
                    continue
                
                signal = signals.get(symbol, {})
                price = float(signal.get("price", 0)) if signal.get("price") else 0.0
                
                if action_type == "buy":
                    # Use position_size from LLM directly
                    shares = llm_action.get("position_size", 0)
                    
                    # If LLM didn't provide position_size, calculate from confidence
                    if shares == 0:
                        base_risk = portfolio_state["total_equity"] * 0.02
                        risk_amount = base_risk * confidence
                        shares = int(risk_amount / price) if price > 0 else 0
                    
                    if shares > 0 and shares * price <= self.cash:
                        actions.append({
                            "symbol": symbol,
                            "action": "buy",
                            "shares": shares,
                            "reason": f"[LLM] {reasoning} (confidence: {confidence:.0%})",
                            "confidence": confidence
                        })
                        print(f"      ✅ BUY {symbol}: {shares} shares @ ${price:.2f} (conf: {confidence:.0%})")
                    else:
                        print(f"      ⚠️  BUY {symbol}: Skip (insufficient cash: need ${shares*price:,.0f}, have ${self.cash:,.0f})")
                
                elif action_type == "sell":
                    if symbol in self.positions and self.positions[symbol] > 0:
                        actions.append({
                            "symbol": symbol,
                            "action": "sell",
                            "shares": self.positions[symbol],
                            "reason": f"[LLM] {reasoning} (confidence: {confidence:.0%})",
                            "confidence": confidence
                        })
                        print(f"      ✅ SELL {symbol}: {self.positions[symbol]} shares @ ${price:.2f} (conf: {confidence:.0%})")
                    else:
                        print(f"      ⚠️  SELL {symbol}: Skip (not in portfolio, only owns: {list(self.positions.keys())})")
                
                # else: HOLD is implicit (don't add to actions)
            
            print(f"   ✅ Total actions: {len(actions)}\n")
            return {"actions": actions}
        
        except Exception as e:
            print(f"\n❌ LLM decision error: {e}")
            print(f"   Falling back to rule-based logic\n")
            return self.make_trading_decision(portfolio_state)
    
    def execute_actions(self, actions: List[Dict], market_data: Dict, timestamp: datetime):
        """Execute trading decisions."""
        for action in actions:
            symbol = action.get("symbol")
            action_type = action.get("action")
            shares = action.get("shares", 0)
            reason = action.get("reason", "")
            
            if symbol not in market_data:
                continue
            
            price = market_data[symbol]["close"]
            
            if action_type == "buy":
                cost = shares * price
                if cost <= self.cash and shares > 0:
                    self.cash -= cost
                    self.positions[symbol] = self.positions.get(symbol, 0) + shares
                    self.entry_prices[symbol] = price
                    self.trades.append({
                        "timestamp": timestamp,
                        "symbol": symbol,
                        "side": "BUY",
                        "shares": shares,
                        "price": price,
                        "cost": cost,
                        "reason": reason
                    })
            
            elif action_type == "sell":
                if symbol in self.positions and self.positions[symbol] > 0:
                    sell_shares = min(shares, self.positions[symbol])
                    proceeds = sell_shares * price
                    self.cash += proceeds
                    self.positions[symbol] -= sell_shares
                    if self.positions[symbol] == 0:
                        del self.positions[symbol]
                        if symbol in self.entry_prices:
                            del self.entry_prices[symbol]
                    self.trades.append({
                        "timestamp": timestamp,
                        "symbol": symbol,
                        "side": "SELL",
                        "shares": sell_shares,
                        "price": price,
                        "proceeds": proceeds,
                        "reason": reason
                    })
    
    def update_equity(self, market_data: Dict, price_cache: Dict = None, timestamp = None):
        """Update equity snapshot using real data or forward-filled prices.
        
        Prefers real data, falls back to last-known price for smooth valuation.
        """
        positions_value = 0
        for symbol, shares in self.positions.items():
            # Prefer real data, fallback to forward-filled cache
            if symbol in market_data:
                price = market_data[symbol]["close"]
            elif price_cache and symbol in price_cache and timestamp in price_cache[symbol]:
                price = price_cache[symbol][timestamp]
            else:
                continue  # Skip if no price available
            
            positions_value += shares * price
        
        total_equity = self.cash + positions_value
        
        self.equity_history.append({
            "timestamp": timestamp,
            "equity": total_equity,
            "cash": self.cash,
            "positions_value": positions_value
        })
    
    def get_equity_curve(self) -> List[Dict]:
        """Return equity history."""
        return self.equity_history


# ============================================================================
# Backtester
# ============================================================================

class HourlyBacktester:
    """Runs hourly backtest with agent and baselines."""
    
    def __init__(self, start_date: str, end_date: str, session_id: str = "legacy-demo-session", use_llm: bool = True, mode: str = "safe_trading"):
        # Validate and swap dates if they're in the wrong order
        from datetime import datetime as dt_parser
        try:
            start = dt_parser.strptime(start_date, "%Y-%m-%d")
            end = dt_parser.strptime(end_date, "%Y-%m-%d")
            
            if start > end:
                print(f"⚠️  Dates were backwards ({start_date} > {end_date}). Swapping...")
                start_date, end_date = end_date, start_date
        except ValueError:
            pass  # Invalid date format, let Alpaca handle the error
        
        self.start_date = start_date
        self.end_date = end_date
        self.session_id = session_id
        self.mode = mode  # "safe_trading" or "buy_and_hold"
        self.data_loader = AlpacaDataLoader()
        self.all_data = {}
        self.use_llm = use_llm and HAS_ANTHROPIC
        self.llm_client = None
        
        # Initialize LLM client if enabled
        if self.use_llm:
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                print("⚠️  ANTHROPIC_API_KEY not set. Running without LLM.")
                self.use_llm = False
            else:
                try:
                    self.llm_client = Anthropic(api_key=api_key)
                    print(f"✅ LLM initialized ({LLM_MODEL_NAME})")
                except Exception as e:
                    print(f"⚠️  Failed to initialize LLM: {e}")
                    self.use_llm = False
    
    def load_data(self):
        """Fetch hourly data from Alpaca."""
        self.all_data = self.data_loader.fetch_bars(DJIA_30, self.start_date, self.end_date)
        if not self.all_data:
            print("❌ No data fetched. Exiting.")
            sys.exit(1)
    
    def calculate_indicators(self):
        """Calculate technical indicators for all symbols."""
        print("\n📈 Calculating technical indicators...")
        count = 0
        for symbol, df in self.all_data.items():
            self.all_data[symbol] = TechnicalIndicators.calculate_indicators(df)
            count += 1
            if count % 5 == 0:
                print(f"  ✅ {count}/{len(self.all_data)} symbols...")
        print(f"  ✅ All indicators calculated\n")
    
    def run_agent_backtest(self) -> Tuple[str, List[Dict]]:
        """Run backtest with agent making hourly decisions."""
        print("🤖 Running Agent backtest (hourly decisions)...\n")
        
        # Track LLM usage for results metadata
        llm_calls_count = 0
        llm_model = "rule-based"  # Default
        
        manager = PortfolioManager(initial_capital=INITIAL_CAPITAL)
        
        # Get all timestamps
        all_timestamps = set()
        for df in self.all_data.values():
            all_timestamps.update(df.index)
        all_timestamps = sorted(all_timestamps)
        
        # Filter: only keep hours with real data for 80%+ of symbols
        min_required = int(len(self.all_data) * 0.8)
        filtered = []
        for ts in all_timestamps:
            real_data_count = sum(1 for df in self.all_data.values() if ts in df.index)
            if real_data_count >= min_required:
                filtered.append(ts)
        
        all_timestamps = filtered if filtered else all_timestamps
        
        # Filter: only keep regular market hours (9:30 AM - 4:00 PM ET)
        # Exclude pre-market (before 9:30 AM) and after-hours (after 4:00 PM)
        import pytz
        et_tz = pytz.timezone('US/Eastern')
        market_hours_only = []
        
        for ts in all_timestamps:
            # Convert to ET
            ts_et = ts.astimezone(et_tz)
            hour = ts_et.hour
            minute = ts_et.minute
            
            # Market hours: 9:30 AM (hour 9, min 30+) through 4:00 PM (hour 16, min 0)
            is_market_hours = (hour > 9 and hour < 16) or \
                             (hour == 9 and minute >= 30) or \
                             (hour == 16 and minute == 0)
            
            if is_market_hours:
                market_hours_only.append(ts)
        
        all_timestamps = market_hours_only
        
        print(f"   Trading {len(all_timestamps)} hours during regular market hours (9:30 AM - 4:00 PM ET)...\n")
        
        # Build forward-filled price cache to handle missing hourly data
        print("   Pre-computing forward-filled price cache...")
        price_cache = {}
        for symbol, df in self.all_data.items():
            price_cache[symbol] = {}
            last_price = None
            
            for timestamp in all_timestamps:
                if timestamp in df.index:
                    last_price = df.loc[timestamp, "close"]
                    price_cache[symbol][timestamp] = last_price
                else:
                    # Fallback (shouldn't happen with daily data)
                    if last_price is not None:
                        price_cache[symbol][timestamp] = last_price
        
        print("   ✅ Cache ready\n")
        
        # Hourly loop
        for i, timestamp in enumerate(all_timestamps):
            # Get market data for this hour (real data when available)
            market_data = {}
            for symbol in DJIA_30:
                if symbol not in self.all_data:
                    continue
                df = self.all_data[symbol]
                if timestamp not in df.index:
                    continue
                market_data[symbol] = df.loc[timestamp]
            
            # Get portfolio state (uses real data for signals, forward-fill for valuation)
            state = manager.get_portfolio_state(market_data, price_cache, timestamp)
            state["timestamp"] = timestamp  # Add timestamp for LLM context
            
            # Make decision (LLM if available, else rule-based)
            if self.use_llm and self.llm_client:
                decision = manager.make_trading_decision_with_llm(state, self.llm_client, mode=self.mode)
                llm_calls_count += 1  # Track that LLM was used
                if llm_calls_count == 1:  # Set on first call
                    llm_model = LLM_MODEL_NAME
            else:
                decision = manager.make_trading_decision(state)
            
            # Execute trades (only if real data available)
            manager.execute_actions(decision["actions"], market_data, timestamp)
            
            # Update equity (uses forward-filled prices for smooth valuation)
            manager.update_equity(market_data, price_cache, timestamp)
            
            # Progress
            if (i + 1) % 100 == 0:
                equity = manager.equity_history[-1]["equity"]
                pct_return = ((equity - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100
                print(f"   Hour {i+1}/{len(all_timestamps)}: Equity ${equity:,.0f} ({pct_return:+.1f}%)")
        
        equity_curve = manager.get_equity_curve()
        
        # Convert timestamps to strings
        for entry in equity_curve:
            if hasattr(entry["timestamp"], "isoformat"):
                entry["timestamp"] = entry["timestamp"].isoformat()
        
        # Store in database
        run_id = f"agent_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        initial_eq = equity_curve[0]["equity"] if equity_curve else INITIAL_CAPITAL
        final_eq = equity_curve[-1]["equity"] if equity_curve else INITIAL_CAPITAL
        total_return = (final_eq - INITIAL_CAPITAL) / INITIAL_CAPITAL
        
        db.insert_run(
            run_id=run_id,
            session_id=self.session_id,
            agent_name="Agent",
            mode="backtest",
            start_date=self.start_date,
            end_date=self.end_date,
            initial_equity=initial_eq,
            final_equity=final_eq,
            total_return=total_return,
            sharpe_ratio=self._calc_sharpe(equity_curve),
            max_drawdown=self._calc_max_dd(equity_curve),
            num_trades=len(manager.trades),
            llm_model=llm_model  # Track which model was used
        )
        
        db.insert_equity_points(run_id, equity_curve)
        
        print(f"\n  ✅ Agent backtest complete")
        print(f"     • Run ID: {run_id}")
        model_display = LLM_MODEL_NAME if llm_calls_count > 0 else "rule-based"
        print(f"     • Model: {model_display} (✅ LLM enabled)" if llm_calls_count > 0 else f"     • Model: {model_display} (❌ fallback)")
        print(f"     • LLM Calls: {llm_calls_count}")
        print(f"     • Trades: {len(manager.trades)}")
        print(f"     • Final: ${final_eq:,.0f}")
        print(f"     • Return: {total_return*100:+.2f}%\n")
        
        return run_id, equity_curve
    
    def run_buyhold_baseline(self) -> Tuple[str, List[Dict]]:
        """Buy and hold baseline using shared baseline generator."""
        print("📊 Running Buy & Hold baseline...\n")
        
        # Use shared baseline generator (10-stock buy-and-hold)
        equity_history, _ = generate_baselines(
            bars_by_symbol=self.all_data,
            start_date=self.start_date,
            end_date=self.end_date,
            initial_capital=INITIAL_CAPITAL,
            symbols_list=TOP_10
        )
        
        if not equity_history:
            return None, []
        
        # Store in database
        run_id = f"buyhold_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        initial_eq = equity_history[0]["equity"]
        final_eq = equity_history[-1]["equity"]
        total_return = (final_eq - INITIAL_CAPITAL) / INITIAL_CAPITAL
        
        db.insert_run(
            run_id=run_id,
            session_id=self.session_id,
            agent_name="buy-and-hold",
            mode="backtest",
            start_date=self.start_date,
            end_date=self.end_date,
            initial_equity=initial_eq,
            final_equity=final_eq,
            total_return=total_return,
            sharpe_ratio=self._calc_sharpe(equity_history),
            max_drawdown=self._calc_max_dd(equity_history),
            num_trades=1
        )
        
        db.insert_equity_points(run_id, equity_history)
        
        print(f"  ✅ Buy & Hold baseline complete")
        print(f"     • Run ID: {run_id}")
        print(f"     • Final: ${final_eq:,.0f}")
        print(f"     • Return: {total_return*100:+.2f}%\n")
        
        return run_id, equity_history
    
    def run_djia_baseline(self) -> Tuple[str, List[Dict]]:
        """DJIA index baseline using shared baseline generator."""
        print("📊 Running DJIA Index baseline...\n")
        
        # Use shared baseline generator (full DJIA 30 stocks - don't filter)
        # DJIA is a market index and should track all 30 stocks regardless of agent mode
        _, equity_history = generate_baselines(
            bars_by_symbol=self.all_data,
            start_date=self.start_date,
            end_date=self.end_date,
            initial_capital=INITIAL_CAPITAL
        )
        
        if not equity_history:
            return None, []
        
        # Store in database
        run_id = f"djia_index_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        initial_eq = equity_history[0]["equity"]
        final_eq = equity_history[-1]["equity"]
        total_return = (final_eq - INITIAL_CAPITAL) / INITIAL_CAPITAL
        
        db.insert_run(
            run_id=run_id,
            session_id=self.session_id,
            agent_name="DJIA",
            mode="backtest",
            start_date=self.start_date,
            end_date=self.end_date,
            initial_equity=initial_eq,
            final_equity=final_eq,
            total_return=total_return,
            sharpe_ratio=self._calc_sharpe(equity_history),
            max_drawdown=self._calc_max_dd(equity_history),
            num_trades=0
        )
        
        db.insert_equity_points(run_id, equity_history)
        
        print(f"  ✅ DJIA Index baseline complete")
        print(f"     • Run ID: {run_id}")
        print(f"     • Final: ${final_eq:,.0f}")
        print(f"     • Return: {total_return*100:+.2f}%\n")
        
        return run_id, equity_history
    
    @staticmethod
    def _calc_sharpe(equity_curve: List[Dict]) -> float:
        """
        Calculate Sharpe ratio from hourly equity curve.
        
        Formula:
            sharpe = (mean(returns) / std(returns)) * sqrt(periods_per_year)
        
        Data is HOURLY, so annualization factor = sqrt(252 * 6.5):
            - 252 = trading days per year
            - 6.5 = trading hours per day (9:30 AM - 4:00 PM ET)
            - Total: sqrt(1638) ≈ 40.47
        
        Returns: float
            Annualized Sharpe ratio. Returns 0 if insufficient data or zero volatility.
        """
        if len(equity_curve) < 2:
            return 0
        
        equities = np.array([e["equity"] for e in equity_curve])
        returns = np.diff(equities) / equities[:-1]
        
        if len(returns) == 0 or np.std(returns) == 0:
            return 0
        
        # Annualize for hourly data: sqrt(252 trading days * 6.5 hours/day)
        annualization_factor = np.sqrt(252 * 6.5)
        return (np.mean(returns) / np.std(returns)) * annualization_factor
    
    @staticmethod
    def _calc_max_dd(equity_curve: List[Dict]) -> float:
        """Calculate max drawdown."""
        if not equity_curve:
            return 0
        
        equities = np.array([e["equity"] for e in equity_curve])
        running_max = equities[0]
        max_dd = 0
        
        for equity in equities:
            if equity > running_max:
                running_max = equity
            dd = (equity - running_max) / running_max
            if dd < max_dd:
                max_dd = dd
        
        return max_dd


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Hourly backtest with Agent vs Baselines (Real Alpaca Data)"
    )
    parser.add_argument("--start", default=DEFAULT_START, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default=DEFAULT_END, help="End date (YYYY-MM-DD)")
    parser.add_argument("--session-id", default="legacy-demo-session", help="Session ID for isolation")
    parser.add_argument("--clear", action="store_true", help="Clear all data first")
    parser.add_argument("--use-llm", action="store_true", default=True, help="Use LLM for trading decisions (default: True)")
    parser.add_argument("--no-llm", dest="use_llm", action="store_false", help="Disable LLM, use rule-based logic")
    parser.add_argument("--mode", default="safe_trading", choices=["safe_trading", "buy_and_hold"], help="Agent mode: 'safe_trading' (risk management) or 'buy_and_hold' (debug)")
    
    args = parser.parse_args()
    
    session_id = args.session_id
    
    # Validate and swap dates if backwards
    from datetime import datetime as dt_parser
    try:
        start = dt_parser.strptime(args.start, "%Y-%m-%d")
        end = dt_parser.strptime(args.end, "%Y-%m-%d")
        
        if start > end:
            print(f"⚠️  Dates were backwards ({args.start} > {args.end}). Swapping...\n")
            args.start, args.end = args.end, args.start
    except ValueError:
        pass  # Invalid format, let it error naturally
    
    if args.clear:
        print("🗑️ Clearing all existing data...\n")
        db.clear_all()
    
    print(f"\n🚀 Hourly Agent Backtest Framework")
    print(f"{'='*70}")
    print(f"Period: {args.start} → {args.end}")
    print(f"Session: {session_id[:8]}...")
    print(f"Stocks: {len(DJIA_30)} (DJIA)")
    print(f"Trading: Hourly (Agent decisions based on indicators)")
    print(f"Capital: ${INITIAL_CAPITAL:,.0f}")
    
    # Show mode
    mode_display = args.mode.replace("_", " ").title()
    print(f"Mode: {mode_display}")
    print(f"{'='*70}\n")
    
    # Initialize backtester (with LLM if available and enabled)
    # Note: dates are validated in __init__ if they somehow got reversed again
    backtester = HourlyBacktester(args.start, args.end, session_id, use_llm=args.use_llm, mode=args.mode)
    
    if backtester.use_llm:
        print(f"🧠 Using {LLM_MODEL_NAME} for trading decisions (Mode: {mode_display})\n")
    else:
        print("⚙️  Using rule-based logic for trading decisions\n")
    
    # Step 1: Load data
    print("1️⃣ Loading historical hourly data from Alpaca...")
    backtester.load_data()
    
    # Step 2: Calculate indicators
    print("\n2️⃣ Calculating technical indicators...")
    backtester.calculate_indicators()
    
    # DEBUG: Show loaded symbols
    print(f"\n📊 DEBUG - Loaded Symbols:")
    print(f"   Total symbols loaded: {len(backtester.all_data)}")
    print(f"   Symbols: {', '.join(sorted(backtester.all_data.keys())[:10])}{'...' if len(backtester.all_data) > 10 else ''}")
    print(f"   Agent will buy: 10 target stocks (AAPL, MSFT, JPM, V, JNJ, UNH, WMT, HD, MA, PG)")
    print(f"   Baselines will buy: ALL {len(backtester.all_data)} symbols equally")
    
    # Step 3: Run backtests
    print("\n3️⃣ Running backtests...\n")
    
    agent_id, agent_eq = backtester.run_agent_backtest()
    
    # DEBUG: Show what agent bought
    print(f"\n📋 DEBUG - Agent Holdings Summary:")
    if agent_eq:
        agent_final = agent_eq[-1]
        print(f"   Final equity: ${agent_final['equity']:,.0f}")
    
    bh_id, bh_eq = backtester.run_buyhold_baseline()
    
    # DEBUG: Show what baseline bought
    print(f"\n📋 DEBUG - Baseline Holdings Summary:")
    if bh_eq:
        bh_final = bh_eq[-1]
        print(f"   Final equity: ${bh_final['equity']:,.0f}")
    
    djia_id, djia_eq = backtester.run_djia_baseline()
    
    # Summary
    print(f"{'='*70}")
    print(f"✅ All backtests complete!")
    print(f"{'='*70}")
    print(f"\nRun IDs:")
    print(f"  • Agent: {agent_id}")
    print(f"  • Buy & Hold: {bh_id}")
    print(f"  • DJIA Index: {djia_id}")
    print(f"\n📊 Dashboard: python3 dashboard/backend/app.py → http://localhost:8000")


if __name__ == "__main__":
    main()
