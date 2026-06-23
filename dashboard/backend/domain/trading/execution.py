"""In-memory order-execution / trade-mutation helpers.

Extracted (Phase 2B3) from ``PortfolioManager.execute_actions`` in
``dashboard/scripts/backtest_hourly_agent.py``. This is pure, domain-level
execution logic over explicit state (cash, positions, entry prices, trades). The
legacy method now delegates here.

Behavior is byte-for-byte identical to the original method. In particular:

* action fields are read with ``action.get("symbol")``, ``action.get("action")``,
  ``action.get("shares", 0)``, ``action.get("reason", "")``;
* a symbol absent from ``market_data`` is skipped (the original ``continue``);
  ``price_cache`` is intentionally NOT consulted here, exactly as before, so this
  module deliberately does NOT reuse ``portfolio.resolve_price``;
* execution price is always ``market_data[symbol]["close"]``;
* BUY executes only when ``cost <= cash and shares > 0``, sets
  ``entry_prices[symbol] = price``, and records a trade with a ``cost`` field;
* SELL executes only when the symbol is held with a positive quantity, sells
  ``min(shares, positions[symbol])``, removes the position and its entry price
  when the holding reaches zero, and records a trade with a ``proceeds`` field
  and ``shares`` equal to the executed quantity;
* HOLD / unknown action types are no-ops;
* a later action is never blocked by an earlier skipped/failed one;
* ``positions``, ``entry_prices`` and ``trades`` are mutated in place; ``cash`` is
  a scalar and is returned so the caller can reassign it.

No "improvements", normalization, or new guards are added: any pre-existing edge
behavior (e.g. zero/negative quantities) is preserved exactly.

This module is domain-only: it must not import FastAPI, Anthropic, Alpaca
clients, the database singleton, API routers, or scripts.
"""

from datetime import datetime
from typing import Dict, List


def execute_actions(
    *,
    actions: List[Dict],
    market_data: Dict,
    timestamp: datetime,
    cash: float,
    positions: Dict,
    entry_prices: Dict,
    trades: List[Dict],
) -> float:
    """Apply ``actions`` to the given portfolio state in place.

    ``positions``, ``entry_prices`` and ``trades`` are mutated in place. ``cash``
    is a scalar and the (possibly updated) value is returned; callers must
    reassign it. The return value is the new cash balance, matching the original
    method's mutation of ``self.cash``.
    """
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
            if cost <= cash and shares > 0:
                cash -= cost
                positions[symbol] = positions.get(symbol, 0) + shares
                entry_prices[symbol] = price
                trades.append({
                    "timestamp": timestamp,
                    "symbol": symbol,
                    "side": "BUY",
                    "shares": shares,
                    "price": price,
                    "cost": cost,
                    "reason": reason
                })

        elif action_type == "sell":
            if symbol in positions and positions[symbol] > 0:
                sell_shares = min(shares, positions[symbol])
                proceeds = sell_shares * price
                cash += proceeds
                positions[symbol] -= sell_shares
                if positions[symbol] == 0:
                    del positions[symbol]
                    if symbol in entry_prices:
                        del entry_prices[symbol]
                trades.append({
                    "timestamp": timestamp,
                    "symbol": symbol,
                    "side": "SELL",
                    "shares": sell_shares,
                    "price": price,
                    "proceeds": proceeds,
                    "reason": reason
                })

    return cash
