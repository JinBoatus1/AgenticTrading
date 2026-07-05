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
import dashboard.backend.infrastructure.llm.token_cost as token_cost
from dashboard.backend.baseline_generator import generate_baselines
from dashboard.backend.infrastructure.llm.validator import create_safe_prompt, create_prompt, validate_llm_response, LLMTradingDecision, TOP_10_STOCKS

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

# `HourlyBacktester` now lives in
# dashboard.backend.domain.backtesting.engine and is re-exported here so the
# legacy public path (bha.HourlyBacktester), main() below, and existing
# subclasses (e.g. backtest_custom_algo) keep working unchanged.
from dashboard.backend.domain.backtesting.engine import HourlyBacktester


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
    parser.add_argument("--strategy-prompt-file", default=None, help="Path to a UTF-8 file with a free-form strategy prompt that REPLACES the built-in agent prompt for this run")
    parser.add_argument("--model", default=None, help="Override the LLM model id (e.g. anthropic/claude-haiku-4-5). Defaults to the gateway-appropriate slug.")
    
    args = parser.parse_args()
    
    session_id = args.session_id

    # Optional free-form strategy prompt (read from a file to avoid shell escaping).
    strategy_prompt = None
    if args.strategy_prompt_file:
        try:
            strategy_prompt = Path(args.strategy_prompt_file).read_text(encoding="utf-8").strip() or None
        except OSError as exc:
            print(f"⚠️  Could not read --strategy-prompt-file ({args.strategy_prompt_file}): {exc}")
            strategy_prompt = None
    
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
    mode_display = "Custom Prompt" if strategy_prompt else args.mode.replace("_", " ").title()
    print(f"Mode: {mode_display}")
    if strategy_prompt:
        print(f"Custom strategy prompt: {len(strategy_prompt)} chars")
    print(f"{'='*70}\n")
    
    # Initialize backtester (with LLM if available and enabled)
    # Note: dates are validated in __init__ if they somehow got reversed again
    backtester = HourlyBacktester(
        args.start,
        args.end,
        session_id,
        use_llm=args.use_llm,
        mode=args.mode,
        strategy_prompt=strategy_prompt,
        model=args.model,
    )
    
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
