"""Characterization tests for the PortfolioManager move (Phase 2C3).

Verifies that ``PortfolioManager`` now lives canonically in
``dashboard.backend.domain.backtesting.portfolio_manager`` and that the legacy
script re-exports the exact same object, with constructor/state/method behavior
unchanged. No external services are called.
"""

import json
from datetime import datetime

import pandas as pd

from dashboard.backend.domain.backtesting.portfolio_manager import (
    PortfolioManager as CanonicalPortfolioManager,
)
from dashboard.scripts import backtest_hourly_agent as bha


def _row(close, **kwargs):
    data = {"close": close}
    data.update(kwargs)
    return pd.Series(data)


# ---------------------------------------------------------------------------
# Identity / re-export
# ---------------------------------------------------------------------------

def test_legacy_reexports_canonical_class():
    assert bha.PortfolioManager is CanonicalPortfolioManager


def test_canonical_module_path():
    assert CanonicalPortfolioManager.__module__ == (
        "dashboard.backend.domain.backtesting.portfolio_manager"
    )


def test_no_separate_legacy_class_object():
    # The script must not define its own duplicate class.
    assert bha.PortfolioManager.__qualname__ == "PortfolioManager"
    assert bha.PortfolioManager is CanonicalPortfolioManager


def test_hourly_backtester_moved_to_engine_in_phase_2c5():
    # Phase 2C5 moved HourlyBacktester to the canonical engine module; the script
    # re-exports the same class object.
    from dashboard.backend.domain.backtesting.engine import HourlyBacktester as Canon

    assert bha.HourlyBacktester is Canon
    assert bha.HourlyBacktester.__module__ == (
        "dashboard.backend.domain.backtesting.engine"
    )


# ---------------------------------------------------------------------------
# Constructor / initial state
# ---------------------------------------------------------------------------

def test_constructor_defaults():
    pm = CanonicalPortfolioManager()
    assert pm.initial_capital == 100000
    assert pm.cash == 100000
    assert pm.positions == {}
    assert pm.entry_prices == {}
    assert pm.trades == []
    assert pm.equity_history == []
    assert pm.llm_calls == 0
    assert pm.input_tokens == 0
    assert pm.output_tokens == 0


def test_constructor_custom_capital():
    pm = CanonicalPortfolioManager(50000)
    assert pm.initial_capital == 50000
    assert pm.cash == 50000


# ---------------------------------------------------------------------------
# Delegation / method behavior (golden)
# ---------------------------------------------------------------------------

def test_get_portfolio_state_delegates():
    pm = CanonicalPortfolioManager(100000)
    pm.positions = {"AAPL": 10}
    pm.entry_prices = {"AAPL": 200.0}
    state = pm.get_portfolio_state({"AAPL": _row(200.0)})
    assert state["positions_value"] == 2000.0
    assert state["total_equity"] == 102000.0


def test_make_trading_decision_delegates():
    pm = CanonicalPortfolioManager(100000)
    state = {
        "total_equity": 100000,
        "market_signals": {"AAPL": {"price": 100.0, "rsi": 25.0, "sma20": 110.0, "sma50": 120.0}},
    }
    out = pm.make_trading_decision(state)
    assert out["actions"][0]["action"] == "buy"


def test_execute_actions_delegates():
    pm = CanonicalPortfolioManager(100000)
    pm.execute_actions(
        [{"symbol": "AAPL", "action": "buy", "shares": 10}],
        {"AAPL": _row(200.0)},
        "t0",
    )
    assert pm.cash == 98000.0
    assert pm.positions == {"AAPL": 10}
    assert pm.trades[0]["side"] == "BUY"


def test_update_equity_and_get_equity_curve_delegate():
    pm = CanonicalPortfolioManager(100000)
    pm.update_equity({}, timestamp="t0")
    curve = pm.get_equity_curve()
    assert curve is pm.equity_history
    assert curve[0] == {"timestamp": "t0", "equity": 100000, "cash": 100000, "positions_value": 0}


# ---------------------------------------------------------------------------
# LLM workflow with a fake client (no network)
# ---------------------------------------------------------------------------

class _FakeUsage:
    def __init__(self, i, o):
        self.input_tokens = i
        self.output_tokens = o


class _FakeResp:
    def __init__(self, text, usage=None):
        self.content = [type("B", (), {"text": text})()]
        self.usage = usage


class _FakeClient:
    def __init__(self, resp):
        self._resp = resp

        class _M:
            @staticmethod
            def create(**kwargs):
                return resp
        self.messages = _M()


def _llm_state():
    return {
        "timestamp": datetime(2026, 1, 1),
        "cash": 100000,
        "positions": [],
        "positions_value": 0,
        "total_equity": 100000,
        "market_signals": {
            "AAPL": {"price": 100.0, "rsi": 25.0, "macd": 1.0, "macd_signal": 0.5,
                     "sma20": 110.0, "sma50": 120.0, "bb_upper": 130.0, "bb_lower": 90.0},
        },
    }


def test_make_trading_decision_with_llm_no_client_fallback():
    pm = CanonicalPortfolioManager(100000)
    out = pm.make_trading_decision_with_llm(_llm_state(), None)
    assert out == pm.make_trading_decision(_llm_state())
    assert pm.llm_calls == 0


def test_make_trading_decision_with_llm_buy_and_tokens():
    pm = CanonicalPortfolioManager(100000)
    resp_text = json.dumps({"actions": [
        {"symbol": "AAPL", "action": "buy", "confidence": 0.9,
         "reasoning": "x", "position_size": 5},
    ]})
    client = _FakeClient(_FakeResp(resp_text, _FakeUsage(12, 8)))
    out = pm.make_trading_decision_with_llm(_llm_state(), client)
    assert out["actions"][0]["action"] == "buy"
    assert pm.input_tokens == 12
    assert pm.output_tokens == 8
    assert pm.llm_calls == 1


# ---------------------------------------------------------------------------
# Subclass compatibility (a fresh subclass)
# ---------------------------------------------------------------------------

def test_simple_subclass_works():
    class MyPM(CanonicalPortfolioManager):
        def custom(self):
            return "ok"

    pm = MyPM(100000)
    pm.execute_actions([{"symbol": "AAPL", "action": "buy", "shares": 1}],
                       {"AAPL": _row(100.0)}, "t0")
    assert pm.cash == 99900.0
    assert pm.custom() == "ok"
    assert [c.__name__ for c in MyPM.__mro__] == ["MyPM", "PortfolioManager", "object"]
