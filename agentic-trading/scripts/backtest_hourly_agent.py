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
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import uuid
import numpy as np
import pandas as pd
import requests

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from database import db
from baseline_generator import generate_baselines

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
        creds_path = Path(__file__).parent.parent / "credentials" / "alpaca.json"
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
        """
        df = df.copy()
        
        try:
            # RSI
            rsi = ta.rsi(df["close"], length=14)
            df["rsi_14"] = rsi
            
            # MACD
            macd = ta.macd(df["close"], fast=12, slow=26, signal=9)
            macd_cols = [c for c in macd.columns if "MACD_12_26_9" in c]
            signal_cols = [c for c in macd.columns if "MACDs_12_26_9" in c]
            if macd_cols:
                df["macd"] = macd[macd_cols[0]]
            if signal_cols:
                df["macd_signal"] = macd[signal_cols[0]]
            
            # Bollinger Bands
            bbands = ta.bbands(df["close"], length=20, std=2)
            bbu_cols = [c for c in bbands.columns if "BBU" in c]
            bbl_cols = [c for c in bbands.columns if "BBL" in c]
            if bbu_cols:
                df["bb_upper"] = bbands[bbu_cols[0]]
            if bbl_cols:
                df["bb_lower"] = bbands[bbl_cols[0]]
            
            # SMAs
            df["sma20"] = ta.sma(df["close"], length=20)
            df["sma50"] = ta.sma(df["close"], length=50)
            
        except Exception as e:
            print(f"Warning: Error calculating indicators: {e}")
        
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
    
    def __init__(self, start_date: str, end_date: str):
        self.start_date = start_date
        self.end_date = end_date
        self.data_loader = AlpacaDataLoader()
        self.all_data = {}
    
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
            
            # Make decision (only on real data signals)
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
            agent_name="Agent",
            mode="backtest",
            start_date=self.start_date,
            end_date=self.end_date,
            initial_equity=initial_eq,
            final_equity=final_eq,
            total_return=total_return,
            sharpe_ratio=self._calc_sharpe(equity_curve),
            max_drawdown=self._calc_max_dd(equity_curve),
            num_trades=len(manager.trades)
        )
        
        db.insert_equity_points(run_id, equity_curve)
        
        print(f"\n  ✅ Agent backtest complete")
        print(f"     • Run ID: {run_id}")
        print(f"     • Trades: {len(manager.trades)}")
        print(f"     • Final: ${final_eq:,.0f}")
        print(f"     • Return: {total_return*100:+.2f}%\n")
        
        return run_id, equity_curve
    
    def run_buyhold_baseline(self) -> Tuple[str, List[Dict]]:
        """Buy and hold baseline using shared baseline generator."""
        print("📊 Running Buy & Hold baseline...\n")
        
        # Use shared baseline generator
        equity_history, _ = generate_baselines(
            bars_by_symbol=self.all_data,
            start_date=self.start_date,
            end_date=self.end_date,
            initial_capital=INITIAL_CAPITAL
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
        
        # Use shared baseline generator
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
        """Calculate Sharpe ratio."""
        if len(equity_curve) < 2:
            return 0
        
        equities = np.array([e["equity"] for e in equity_curve])
        returns = np.diff(equities) / equities[:-1]
        
        if len(returns) == 0 or np.std(returns) == 0:
            return 0
        
        return (np.mean(returns) / np.std(returns)) * np.sqrt(252)
    
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
    parser.add_argument("--clear", action="store_true", help="Clear all data first")
    
    args = parser.parse_args()
    
    if args.clear:
        print("🗑️ Clearing all existing data...\n")
        db.clear_all()
    
    print(f"\n🚀 Hourly Agent Backtest Framework")
    print(f"{'='*70}")
    print(f"Period: {args.start} → {args.end}")
    print(f"Stocks: {len(DJIA_30)} (DJIA)")
    print(f"Trading: Hourly (Agent decisions based on indicators)")
    print(f"Capital: ${INITIAL_CAPITAL:,.0f}")
    print(f"{'='*70}\n")
    
    # Initialize backtester
    backtester = HourlyBacktester(args.start, args.end)
    
    # Step 1: Load data
    print("1️⃣ Loading historical hourly data from Alpaca...")
    backtester.load_data()
    
    # Step 2: Calculate indicators
    print("\n2️⃣ Calculating technical indicators...")
    backtester.calculate_indicators()
    
    # Step 3: Run backtests
    print("3️⃣ Running backtests...\n")
    
    agent_id, agent_eq = backtester.run_agent_backtest()
    bh_id, bh_eq = backtester.run_buyhold_baseline()
    djia_id, djia_eq = backtester.run_djia_baseline()
    
    # Summary
    print(f"{'='*70}")
    print(f"✅ All backtests complete!")
    print(f"{'='*70}")
    print(f"\nRun IDs:")
    print(f"  • Agent: {agent_id}")
    print(f"  • Buy & Hold: {bh_id}")
    print(f"  • DJIA Index: {djia_id}")
    print(f"\n📊 Dashboard: python3 backend/app.py → http://localhost:8000")


if __name__ == "__main__":
    main()
