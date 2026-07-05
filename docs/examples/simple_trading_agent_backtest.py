#!/usr/bin/env python3
"""
Build a Simple Trading Agent — hourly DJIA backtest with CommonStack + Alpaca.

  Alpaca hourly bars → LLM agent (CommonStack) → simulate trades → metrics

Setup:
  pip install alpaca-py anthropic pandas pytz

  export ALPACA_API_KEY=...
  export ALPACA_SECRET_KEY=...
  export COMMONSTACK_API_KEY=...

Run:
  python simple_trading_agent_backtest.py
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List

import pandas as pd
import pytz

# ---------------------------------------------------------------------------
# 1. Config
# ---------------------------------------------------------------------------

DJIA_30 = [
    "AAPL", "MSFT", "JPM", "V", "JNJ", "WMT", "PG", "MA", "HD", "DIS",
    "MCD", "PFE", "CSCO", "IBM", "INTC", "XOM", "AXP", "KO", "CAT", "GS",
    "MRK", "NVDA", "BA", "UNH", "MMM", "CVX", "NKE", "AMGN", "TRV", "WBA",
]

START = "2026-06-01"
END = "2026-06-08"  # one week

INITIAL_CASH = 100_000.0
COMMONSTACK_BASE = os.getenv("COMMONSTACK_BASE_URL", "https://api.commonstack.ai")
MODEL = os.getenv("COMMONSTACK_MODEL", "anthropic/claude-haiku-4-5")

ET = pytz.timezone("US/Eastern")

SYSTEM_PROMPT = """You are a DJIA hourly trading agent.
Return ONLY valid JSON with an "actions" array. No markdown, no extra text.
Each action: action (buy|sell|hold), symbol, confidence (0-1), reasoning, position_size (integer shares, 0 for hold).
Only sell symbols you currently own. Use symbols from the snapshot only."""


# ---------------------------------------------------------------------------
# 2. Fetch hourly bars from Alpaca
# ---------------------------------------------------------------------------

def fetch_hourly_bars(symbols: List[str], start: str, end: str) -> Dict[str, pd.DataFrame]:
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    api_key = os.getenv("ALPACA_API_KEY")
    secret = os.getenv("ALPACA_SECRET_KEY")
    if not api_key or not secret:
        raise SystemExit("Set ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables.")

    client = StockHistoricalDataClient(api_key, secret)
    req = StockBarsRequest(
        symbol_or_symbols=symbols,
        timeframe=TimeFrame.Hour,
        start=start,
        end=end,
    )
    bars = client.get_stock_bars(req).df

    out: Dict[str, pd.DataFrame] = {}
    for sym in symbols:
        if sym not in bars.index.get_level_values(0):
            continue
        df = bars.xs(sym)[["close"]].copy()
        df.index = pd.to_datetime(df.index)
        out[sym] = df.sort_index()
    return out


def is_market_hour(ts: pd.Timestamp) -> bool:
    t = ts.astimezone(ET)
    if t.weekday() >= 5:
        return False
    minutes = t.hour * 60 + t.minute
    return 9 * 60 + 30 <= minutes <= 16 * 60


def market_timestamps(data: Dict[str, pd.DataFrame]) -> List[pd.Timestamp]:
    all_ts = sorted({ts for df in data.values() for ts in df.index})
    return [ts for ts in all_ts if is_market_hour(ts)]


# ---------------------------------------------------------------------------
# 3. Portfolio simulation
# ---------------------------------------------------------------------------

@dataclass
class Portfolio:
    cash: float = INITIAL_CASH
    positions: Dict[str, int] = field(default_factory=dict)
    trades: List[dict] = field(default_factory=list)
    equity_curve: List[dict] = field(default_factory=list)

    def mark_equity(self, prices: Dict[str, float], ts: pd.Timestamp) -> None:
        pos_val = sum(self.positions.get(s, 0) * prices.get(s, 0) for s in self.positions)
        self.equity_curve.append({"timestamp": ts, "equity": self.cash + pos_val})

    def execute(self, actions: List[dict], prices: Dict[str, float], ts: pd.Timestamp) -> None:
        for act in actions:
            sym = act.get("symbol")
            side = str(act.get("action", "hold")).lower()
            shares = int(act.get("position_size") or 0)
            if not sym or sym not in prices or shares <= 0:
                continue
            price = prices[sym]
            if side == "buy" and shares * price <= self.cash:
                self.cash -= shares * price
                self.positions[sym] = self.positions.get(sym, 0) + shares
                self.trades.append({"ts": ts, "symbol": sym, "side": "BUY", "shares": shares, "price": price})
            elif side == "sell" and self.positions.get(sym, 0) > 0:
                qty = min(shares, self.positions[sym])
                self.cash += qty * price
                self.positions[sym] -= qty
                if self.positions[sym] == 0:
                    del self.positions[sym]
                self.trades.append({"ts": ts, "symbol": sym, "side": "SELL", "shares": qty, "price": price})


def build_snapshot(portfolio: Portfolio, prices: Dict[str, float], ts: pd.Timestamp) -> dict:
    return {
        "timestamp": ts.isoformat(),
        "cash": round(portfolio.cash, 2),
        "holdings": {
            s: {"shares": q, "price": prices[s]}
            for s, q in portfolio.positions.items() if s in prices
        },
        "prices": {s: round(p, 2) for s, p in sorted(prices.items())},
    }


# ---------------------------------------------------------------------------
# 4. LLM agent via CommonStack (Anthropic-compatible route)
# ---------------------------------------------------------------------------

def make_llm_client():
    key = os.getenv("COMMONSTACK_API_KEY")
    if not key:
        return None
    from anthropic import Anthropic
    return Anthropic(api_key=key, base_url=COMMONSTACK_BASE)


def build_prompt(snapshot: dict) -> str:
    return f"""You manage a DJIA portfolio. Decide what to buy, sell, or hold this hour.

Rules:
- Use only symbols and prices in the snapshot.
- SELL only symbols you currently own.
- position_size = integer shares; keep each new buy under 10% of cash.
- Output at most 5 non-hold actions.

Snapshot:
{json.dumps(snapshot, indent=2)}

Return ONLY:
{{"actions": [{{"action": "buy|sell|hold", "symbol": "AAPL", "confidence": 0.7, "reasoning": "...", "position_size": 10}}]}}"""


def parse_actions(text: str) -> List[dict]:
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}") + 1
    if start < 0 or end <= 0:
        return []
    try:
        data = json.loads(cleaned[start:end])
    except json.JSONDecodeError:
        return []
    return [
        {
            "symbol": a.get("symbol"),
            "action": a.get("action", "hold"),
            "position_size": int(a.get("position_size") or 0),
        }
        for a in data.get("actions", [])
    ]


def rule_based_decision(snapshot: dict) -> List[dict]:
    """Fallback: equal-weight buy 5 names on the first step, then hold."""
    if snapshot["holdings"]:
        return []
    actions = []
    picks = list(snapshot["prices"].items())[:5]
    budget = snapshot["cash"] / len(picks)
    for sym, price in picks:
        shares = int(budget / price)
        if shares > 0:
            actions.append({"symbol": sym, "action": "buy", "position_size": shares})
    return actions


def ask_agent(client, snapshot: dict) -> List[dict]:
    if client is None:
        return rule_based_decision(snapshot)
    resp = client.messages.create(
        model=MODEL,
        max_tokens=800,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_prompt(snapshot)}],
    )
    return parse_actions(resp.content[0].text)


# ---------------------------------------------------------------------------
# 5. Backtest loop
# ---------------------------------------------------------------------------

def run_backtest(use_llm: bool = True) -> dict:
    print(f"Fetching DJIA hourly bars ({START} → {END})...")
    data = fetch_hourly_bars(DJIA_30, START, END)
    timestamps = market_timestamps(data)
    print(f"Loaded {len(data)} symbols, {len(timestamps)} market hours.")

    client = make_llm_client() if use_llm else None
    if use_llm and client is None:
        print("No COMMONSTACK_API_KEY — using rule-based fallback.")

    portfolio = Portfolio()
    for i, ts in enumerate(timestamps, 1):
        prices = {
            sym: float(df.loc[ts, "close"])
            for sym, df in data.items()
            if ts in df.index
        }
        if not prices:
            continue

        snapshot = build_snapshot(portfolio, prices, ts)
        portfolio.execute(ask_agent(client, snapshot), prices, ts)
        portfolio.mark_equity(prices, ts)

        if i % 10 == 0 or i == len(timestamps):
            eq = portfolio.equity_curve[-1]["equity"]
            print(f"  step {i}/{len(timestamps)}  equity ${eq:,.0f}  trades {len(portfolio.trades)}")

    return summarize(portfolio)


def summarize(portfolio: Portfolio) -> dict:
    if not portfolio.equity_curve:
        return {"return_pct": 0.0, "trades": 0}

    start_eq = INITIAL_CASH
    end_eq = portfolio.equity_curve[-1]["equity"]
    ret = (end_eq - start_eq) / start_eq * 100

    result = {
        "initial_cash": start_eq,
        "final_equity": round(end_eq, 2),
        "return_pct": round(ret, 3),
        "trades": len(portfolio.trades),
    }
    print("\n=== Results ===")
    for k, v in result.items():
        print(f"  {k}: {v}")
    return result


# ---------------------------------------------------------------------------
# 6. Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Simple DJIA hourly backtest")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM; use rule-based agent")
    args = parser.parse_args()
    run_backtest(use_llm=not args.no_llm)


if __name__ == "__main__":
    main()
