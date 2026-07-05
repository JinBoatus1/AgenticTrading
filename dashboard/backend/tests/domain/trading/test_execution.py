"""Characterization tests for extracted order execution (Phase 2B3).

Locks in the exact behavior of
``dashboard.backend.domain.trading.execution.execute_actions`` and the legacy
``PortfolioManager.execute_actions`` that delegates to it. Imports use the
canonical package path; no external services are touched.
"""

import pandas as pd

from dashboard.backend.domain.trading.execution import execute_actions
from dashboard.scripts import backtest_hourly_agent as bha


def _row(close, **kwargs):
    data = {"close": close}
    data.update(kwargs)
    return pd.Series(data)


def _state(cash=100000, positions=None, entry_prices=None, trades=None):
    return {
        "cash": cash,
        "positions": dict(positions or {}),
        "entry_prices": dict(entry_prices or {}),
        "trades": list(trades if trades is not None else []),
    }


def _run(actions, market_data, timestamp="t0", **state):
    st = _state(**state)
    st["cash"] = execute_actions(
        actions=actions,
        market_data=market_data,
        timestamp=timestamp,
        cash=st["cash"],
        positions=st["positions"],
        entry_prices=st["entry_prices"],
        trades=st["trades"],
    )
    return st


# ---------------------------------------------------------------------------
# HOLD / no-op
# ---------------------------------------------------------------------------

def test_empty_action_list_noop():
    md = {"AAPL": _row(200.0)}
    st = _run([], md)
    assert st["cash"] == 100000
    assert st["positions"] == {}
    assert st["trades"] == []


def test_hold_action_noop():
    md = {"AAPL": _row(200.0)}
    st = _run([{"symbol": "AAPL", "action": "hold", "shares": 10}], md,
              positions={"AAPL": 5}, entry_prices={"AAPL": 100.0})
    assert st["cash"] == 100000
    assert st["positions"] == {"AAPL": 5}
    assert st["trades"] == []


def test_unknown_action_type_noop():
    md = {"AAPL": _row(200.0)}
    st = _run([{"symbol": "AAPL", "action": "rebalance", "shares": 10}], md)
    assert st["cash"] == 100000
    assert st["positions"] == {}
    assert st["trades"] == []


# ---------------------------------------------------------------------------
# BUY
# ---------------------------------------------------------------------------

def test_valid_buy():
    md = {"AAPL": _row(200.0)}
    st = _run([{"symbol": "AAPL", "action": "buy", "shares": 10, "reason": "r"}], md)
    assert st["cash"] == 98000.0
    assert st["positions"] == {"AAPL": 10}
    assert st["entry_prices"] == {"AAPL": 200.0}
    assert st["trades"] == [{
        "timestamp": "t0",
        "symbol": "AAPL",
        "side": "BUY",
        "shares": 10,
        "price": 200.0,
        "cost": 2000.0,
        "reason": "r",
    }]


def test_buy_default_reason_empty():
    md = {"AAPL": _row(200.0)}
    st = _run([{"symbol": "AAPL", "action": "buy", "shares": 1}], md)
    assert st["trades"][0]["reason"] == ""


def test_multiple_buys_accumulate_position():
    md = {"AAPL": _row(200.0)}
    st = _run([
        {"symbol": "AAPL", "action": "buy", "shares": 10},
        {"symbol": "AAPL", "action": "buy", "shares": 5},
    ], md)
    assert st["positions"] == {"AAPL": 15}
    # entry price overwritten with last buy price
    assert st["entry_prices"] == {"AAPL": 200.0}
    assert st["cash"] == 100000 - 3000.0
    assert len(st["trades"]) == 2


def test_buy_exact_available_cash():
    md = {"AAPL": _row(100.0)}
    st = _run([{"symbol": "AAPL", "action": "buy", "shares": 1000}], md, cash=100000)
    assert st["cash"] == 0
    assert st["positions"] == {"AAPL": 1000}


def test_insufficient_cash_skips_buy():
    md = {"AAPL": _row(200.0)}
    st = _run([{"symbol": "AAPL", "action": "buy", "shares": 1000}], md, cash=1000)
    assert st["cash"] == 1000
    assert st["positions"] == {}
    assert st["trades"] == []


def test_buy_missing_symbol_skipped():
    md = {"AAPL": _row(200.0)}
    st = _run([{"symbol": "TSLA", "action": "buy", "shares": 10}], md)
    assert st["cash"] == 100000
    assert st["positions"] == {}
    assert st["trades"] == []


def test_buy_zero_shares_skipped():
    md = {"AAPL": _row(200.0)}
    st = _run([{"symbol": "AAPL", "action": "buy", "shares": 0}], md)
    assert st["cash"] == 100000
    assert st["positions"] == {}
    assert st["trades"] == []


def test_buy_missing_shares_defaults_zero_skipped():
    md = {"AAPL": _row(200.0)}
    st = _run([{"symbol": "AAPL", "action": "buy"}], md)
    assert st["cash"] == 100000
    assert st["trades"] == []


def test_buy_negative_shares_skipped():
    md = {"AAPL": _row(200.0)}
    st = _run([{"symbol": "AAPL", "action": "buy", "shares": -10}], md)
    assert st["cash"] == 100000
    assert st["positions"] == {}
    assert st["trades"] == []


def test_buy_fractional_shares():
    md = {"AAPL": _row(200.0)}
    st = _run([{"symbol": "AAPL", "action": "buy", "shares": 2.5}], md)
    assert st["positions"] == {"AAPL": 2.5}
    assert st["cash"] == 100000 - 500.0
    assert st["trades"][0]["shares"] == 2.5


# ---------------------------------------------------------------------------
# SELL
# ---------------------------------------------------------------------------

def test_valid_full_sell_removes_position():
    md = {"AAPL": _row(250.0)}
    st = _run([{"symbol": "AAPL", "action": "sell", "shares": 10, "reason": "x"}], md,
              positions={"AAPL": 10}, entry_prices={"AAPL": 200.0})
    assert st["cash"] == 100000 + 2500.0
    assert st["positions"] == {}
    assert st["entry_prices"] == {}
    assert st["trades"] == [{
        "timestamp": "t0",
        "symbol": "AAPL",
        "side": "SELL",
        "shares": 10,
        "price": 250.0,
        "proceeds": 2500.0,
        "reason": "x",
    }]


def test_partial_sell_keeps_position():
    md = {"AAPL": _row(250.0)}
    st = _run([{"symbol": "AAPL", "action": "sell", "shares": 4}], md,
              positions={"AAPL": 10}, entry_prices={"AAPL": 200.0})
    assert st["positions"] == {"AAPL": 6}
    assert st["entry_prices"] == {"AAPL": 200.0}
    assert st["cash"] == 100000 + 1000.0
    assert st["trades"][0]["shares"] == 4


def test_sell_more_than_held_caps_at_holding():
    md = {"AAPL": _row(250.0)}
    st = _run([{"symbol": "AAPL", "action": "sell", "shares": 999}], md,
              positions={"AAPL": 10}, entry_prices={"AAPL": 200.0})
    assert st["positions"] == {}
    assert st["cash"] == 100000 + 2500.0
    assert st["trades"][0]["shares"] == 10


def test_sell_missing_position_skipped():
    md = {"AAPL": _row(250.0)}
    st = _run([{"symbol": "AAPL", "action": "sell", "shares": 5}], md)
    assert st["cash"] == 100000
    assert st["positions"] == {}
    assert st["trades"] == []


def test_sell_zero_shares_appends_trade_no_change():
    # min(0, 10) == 0 -> proceeds 0, position unchanged, but a trade IS appended.
    md = {"AAPL": _row(250.0)}
    st = _run([{"symbol": "AAPL", "action": "sell", "shares": 0}], md,
              positions={"AAPL": 10}, entry_prices={"AAPL": 200.0})
    assert st["cash"] == 100000
    assert st["positions"] == {"AAPL": 10}
    assert len(st["trades"]) == 1
    assert st["trades"][0]["shares"] == 0
    assert st["trades"][0]["proceeds"] == 0


def test_sell_missing_shares_defaults_zero_appends_trade():
    md = {"AAPL": _row(250.0)}
    st = _run([{"symbol": "AAPL", "action": "sell"}], md,
              positions={"AAPL": 10})
    assert st["positions"] == {"AAPL": 10}
    assert len(st["trades"]) == 1
    assert st["trades"][0]["shares"] == 0


def test_multiple_sells():
    md = {"AAPL": _row(250.0)}
    st = _run([
        {"symbol": "AAPL", "action": "sell", "shares": 3},
        {"symbol": "AAPL", "action": "sell", "shares": 3},
    ], md, positions={"AAPL": 10}, entry_prices={"AAPL": 200.0})
    assert st["positions"] == {"AAPL": 4}
    assert len(st["trades"]) == 2


# ---------------------------------------------------------------------------
# Mixed / ordering / partial execution
# ---------------------------------------------------------------------------

def test_buy_then_sell_order_preserved():
    md = {"AAPL": _row(200.0)}
    st = _run([
        {"symbol": "AAPL", "action": "buy", "shares": 10},
        {"symbol": "AAPL", "action": "sell", "shares": 4},
    ], md)
    assert st["positions"] == {"AAPL": 6}
    assert [t["side"] for t in st["trades"]] == ["BUY", "SELL"]


def test_invalid_action_does_not_block_later_actions():
    md = {"AAPL": _row(200.0), "MSFT": _row(400.0)}
    st = _run([
        {"symbol": "TSLA", "action": "buy", "shares": 10},   # missing symbol -> skip
        {"symbol": "AAPL", "action": "buy", "shares": 10},   # valid
    ], md)
    assert st["positions"] == {"AAPL": 10}
    assert len(st["trades"]) == 1


def test_multiple_symbols():
    md = {"AAPL": _row(200.0), "MSFT": _row(400.0)}
    st = _run([
        {"symbol": "AAPL", "action": "buy", "shares": 10},
        {"symbol": "MSFT", "action": "buy", "shares": 5},
    ], md)
    assert st["positions"] == {"AAPL": 10, "MSFT": 5}
    assert st["cash"] == 100000 - 2000.0 - 2000.0


# ---------------------------------------------------------------------------
# Trade records appended in place, earlier records unchanged
# ---------------------------------------------------------------------------

def test_existing_trades_preserved_and_appended_in_place():
    md = {"AAPL": _row(200.0)}
    prior = {"timestamp": "old", "symbol": "X", "side": "BUY"}
    trades = [prior]
    st = _state(trades=trades)
    # use the same list object to confirm in-place append
    st["cash"] = execute_actions(
        actions=[{"symbol": "AAPL", "action": "buy", "shares": 1}],
        market_data=md,
        timestamp="t0",
        cash=st["cash"],
        positions=st["positions"],
        entry_prices=st["entry_prices"],
        trades=trades,
    )
    assert trades[0] is prior
    assert len(trades) == 2
    assert trades[1]["symbol"] == "AAPL"


# ---------------------------------------------------------------------------
# No price_cache fallback (distinct from portfolio valuation helpers)
# ---------------------------------------------------------------------------

def test_execution_ignores_price_cache_semantics():
    # Symbol not in market_data is always skipped; execution has no cache param.
    md = {}
    st = _run([{"symbol": "AAPL", "action": "buy", "shares": 10}], md)
    assert st["positions"] == {}
    assert st["trades"] == []


# ---------------------------------------------------------------------------
# Legacy equivalence: PortfolioManager.execute_actions delegates identically
# ---------------------------------------------------------------------------

def _golden_actions():
    return [
        {"symbol": "AAPL", "action": "buy", "shares": 10, "reason": "a"},
        {"symbol": "MSFT", "action": "buy", "shares": 5, "reason": "b"},
        {"symbol": "AAPL", "action": "sell", "shares": 4, "reason": "c"},
        {"symbol": "TSLA", "action": "buy", "shares": 1},      # missing symbol -> skip
        {"symbol": "MSFT", "action": "hold", "shares": 99},    # no-op
    ]


def _golden_md():
    return {"AAPL": _row(200.0), "MSFT": _row(400.0)}


def test_legacy_method_matches_canonical_helper():
    actions = _golden_actions()
    md = _golden_md()

    # Legacy path
    pm = bha.PortfolioManager(100000)
    assert pm.execute_actions(actions, md, "t0") is None  # returns None
    legacy = {
        "cash": pm.cash,
        "positions": pm.positions,
        "entry_prices": pm.entry_prices,
        "trades": pm.trades,
    }

    # Canonical path with identical inputs
    canon = _run(actions, md, timestamp="t0")

    assert legacy["cash"] == canon["cash"]
    assert legacy["positions"] == canon["positions"]
    assert legacy["entry_prices"] == canon["entry_prices"]
    assert legacy["trades"] == canon["trades"]


def test_legacy_golden_exact_values():
    pm = bha.PortfolioManager(100000)
    pm.execute_actions(_golden_actions(), _golden_md(), "t0")
    # AAPL: buy 10 @200 (-2000), sell 4 @200 (+800) -> 6 shares
    # MSFT: buy 5 @400 (-2000) -> 5 shares
    assert pm.cash == 100000 - 2000 + 800 - 2000
    assert pm.positions == {"AAPL": 6, "MSFT": 5}
    assert pm.entry_prices == {"AAPL": 200.0, "MSFT": 400.0}
    assert [(t["side"], t["symbol"], t["shares"]) for t in pm.trades] == [
        ("BUY", "AAPL", 10),
        ("BUY", "MSFT", 5),
        ("SELL", "AAPL", 4),
    ]


def test_subclass_inherits_execute_actions():
    class MyPM(bha.PortfolioManager):
        def custom_method(self):
            return "ok"

    pm = MyPM(100000)
    pm.execute_actions(
        [{"symbol": "AAPL", "action": "buy", "shares": 10}],
        {"AAPL": _row(200.0)},
        "t0",
    )
    assert pm.cash == 98000.0
    assert pm.positions == {"AAPL": 10}
    assert pm.custom_method() == "ok"
    # execute_actions resolves through the subclass MRO to the script-defined method
    assert MyPM.execute_actions is bha.PortfolioManager.execute_actions
