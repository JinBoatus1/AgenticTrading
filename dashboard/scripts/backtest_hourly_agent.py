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

# Bootstrap for non-package execution contexts: when this module is run directly
# as a file (``python dashboard/scripts/backtest_hourly_agent.py``) or imported
# flat by the backend (``import backtest_hourly_agent`` after the backend adds
# SCRIPTS_DIR to the import path), the repository root is not necessarily
# importable, so the canonical ``dashboard.backend.*`` imports below would fail.
# In those cases
# ``__package__`` is empty and we use the shared script bootstrap helper. When
# this module is imported as ``dashboard.scripts.backtest_hourly_agent`` the repo
# root is already importable and no bootstrap (or extra sys.path entry) is needed.
if not __package__:
    from _bootstrap import ensure_repo_root

    ensure_repo_root()

from dashboard.backend.paths import CREDENTIALS_DIR
from dashboard.backend.database import db
import dashboard.backend.token_cost as token_cost
from dashboard.backend.baseline_generator import generate_baselines
from dashboard.backend.llm_validator import create_safe_prompt, create_prompt, validate_llm_response, LLMTradingDecision, TOP_10_STOCKS

# Optional: LLM integration. Phase 2C2 moved the Anthropic SDK import, the
# default model name, and the LLM request/parse workflow into the canonical
# harness at dashboard.backend.infrastructure.llm.backtest_harness. These symbols
# are re-exported here so existing consumers (engines/strategies/llm_agent.py,
# backtest_custom_algo.py, and bha.* callers) keep working unchanged.
from dashboard.backend.infrastructure.llm.backtest_harness import (
    Anthropic,
    HAS_ANTHROPIC,
    LLM_MODEL_NAME,
)

try:
    import pandas_ta as ta
except ImportError:
    print("Installing pandas_ta...")
    import subprocess
    subprocess.check_call(["pip", "install", "pandas_ta"])
    import pandas_ta as ta

# ---------------------------------------------------------------------------
# Phase 2A extraction: the implementations below now live under the canonical
# dashboard.backend.* packages and are re-exported here so this script's public
# compatibility surface (and the three backend callers that import this module)
# stays unchanged. pandas_ta is imported above first so the features module can
# rely on it being available.
# ---------------------------------------------------------------------------
from dashboard.backend.domain.backtesting.features import TechnicalIndicators
from dashboard.backend.domain.backtesting.metrics import (
    calculate_sharpe,
    calculate_max_drawdown,
)
from dashboard.backend.infrastructure.llm.decision_parsing import fix_json_formatting
from dashboard.backend.infrastructure.market_data.alpaca_bars import AlpacaDataLoader
from dashboard.backend.domain.backtesting.constants import INITIAL_CAPITAL

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
# `fix_json_formatting` now lives in
# dashboard.backend.infrastructure.llm.decision_parsing and is re-exported above.


# ============================================================================
# LLM Model Configuration
# ============================================================================
# `LLM_MODEL_NAME` now lives in
# dashboard.backend.infrastructure.llm.backtest_harness and is re-exported above.

# ============================================================================
# Configuration
# ============================================================================

DEFAULT_START = "2026-03-01"
DEFAULT_END = "2026-04-13"
# `INITIAL_CAPITAL` now lives in
# dashboard.backend.domain.backtesting.constants and is re-exported above.
TIMEFRAME = "1h"  # Hourly


# ============================================================================
# Data Loader - Alpaca API
# ============================================================================
# `AlpacaDataLoader` now lives in
# dashboard.backend.infrastructure.market_data.alpaca_bars and is re-exported above.


# ============================================================================
# Technical Indicators
# ============================================================================
# `TechnicalIndicators` now lives in
# dashboard.backend.domain.backtesting.features and is re-exported above.


# ============================================================================
# Portfolio Manager with Agent Decision Logic
# ============================================================================

# `PortfolioManager` now lives in
# dashboard.backend.domain.backtesting.portfolio_manager and is re-exported
# here so the legacy public path (bha.PortfolioManager) and existing
# subclasses (e.g. backtest_custom_algo) keep working unchanged.
from dashboard.backend.domain.backtesting.portfolio_manager import (
    PortfolioManager,
)


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

        est_cost = token_cost.estimate_cost_usd(
            llm_model, manager.input_tokens, manager.output_tokens
        )

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
            llm_model=llm_model,  # Track which model was used
            llm_calls=manager.llm_calls,
            input_tokens=manager.input_tokens,
            output_tokens=manager.output_tokens,
            est_cost_usd=est_cost,
        )
        
        db.insert_equity_points(run_id, equity_curve)
        
        print(f"\n  ✅ Agent backtest complete")
        print(f"     • Run ID: {run_id}")
        model_display = LLM_MODEL_NAME if llm_calls_count > 0 else "rule-based"
        print(f"     • Model: {model_display} (✅ LLM enabled)" if llm_calls_count > 0 else f"     • Model: {model_display} (❌ fallback)")
        print(f"     • LLM Calls: {llm_calls_count}")
        print(f"     • Tokens: {manager.input_tokens:,} in / {manager.output_tokens:,} out (est. cost ${est_cost:.4f})")
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
        """Annualized hourly Sharpe ratio.

        Delegates to dashboard.backend.domain.backtesting.metrics.calculate_sharpe;
        inputs, outputs, edge cases, and the hourly annualization factor are
        unchanged.
        """
        return calculate_sharpe(equity_curve)

    @staticmethod
    def _calc_max_dd(equity_curve: List[Dict]) -> float:
        """Maximum drawdown of the equity curve.

        Delegates to
        dashboard.backend.domain.backtesting.metrics.calculate_max_drawdown.
        """
        return calculate_max_drawdown(equity_curve)


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
