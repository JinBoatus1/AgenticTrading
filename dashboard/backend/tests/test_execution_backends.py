import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest  # noqa: E402

from execution.base import ExecutionBackend  # noqa: E402
from execution.paper_backend import PaperBackend  # noqa: E402


def test_execution_backend_is_abstract():
    with pytest.raises(TypeError):
        ExecutionBackend()  # abstract — cannot instantiate


def test_paper_backend_is_designed_for_stub():
    backend = PaperBackend()
    assert backend.loop == "realtime"
    with pytest.raises(NotImplementedError):
        backend.build_context()


import pandas as pd  # noqa: E402

import execution.backtest_backend as bb_mod  # noqa: E402
from execution.backtest_backend import BacktestBackend, load_news_sentiment  # noqa: E402
from api.v2.models import ContextEnvelope, SubmitAck  # noqa: E402


def test_news_sentiment_fail_closed_when_plan1_absent(monkeypatch):
    # No integrations.news_sentiment module → slot present, empty, overview None.
    sentiment, overview = load_news_sentiment(["AAPL"], "2026-04-15T10:30:00+00:00")
    assert sentiment == {} and overview is None


def _synthetic_bars(symbols, periods=40):
    idx = pd.date_range("2026-04-15 13:30", periods=periods, freq="h", tz="UTC")
    data = {}
    for i, sym in enumerate(symbols):
        base = 100 + i * 10
        df = pd.DataFrame({
            "open": base, "high": base + 1, "low": base - 1,
            "close": [base + (j % 5) for j in range(periods)],
            "volume": 1000,
        }, index=idx)
        data[sym] = df
    return data


def test_backtest_backend_emits_typed_context(monkeypatch):
    symbols = ["AAPL", "MSFT", "JPM"]

    class _Loader:
        def fetch_bars(self, syms, start, end):
            return _synthetic_bars(symbols)

    monkeypatch.setattr(bb_mod.bha, "AlpacaDataLoader", lambda: _Loader())
    monkeypatch.setattr(bb_mod, "DJIA_30", symbols, raising=False)

    backend = BacktestBackend(
        run_id="run_test_1", session_id="sess_1", agent_name="a",
        model_name="m", start_date="2026-04-15", end_date="2026-04-16",
    )
    backend.load_blocking()  # synchronous load for the test
    assert backend.loop == "lockstep"

    ctx = backend.build_context()
    # Slot guaranteed and the whole envelope validates against the typed model.
    assert "news_sentiment" in ctx
    ContextEnvelope.model_validate(ctx)

    ack = backend.apply_decisions([
        {"action": "hold", "symbol": "AAPL", "confidence": 0.4,
         "reasoning": "hold steady", "position_size": 0},
    ])
    SubmitAck.model_validate(ack)
    assert ack["accepted"] is True
