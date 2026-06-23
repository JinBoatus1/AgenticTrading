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


def test_news_sentiment_fail_closed_when_loader_raises(monkeypatch):
    # Plan 1 adapter exists but throws at call time → still fail-closed.
    import types

    fake = types.ModuleType("integrations.news_sentiment")

    def _boom(universe, timestamp):
        raise RuntimeError("news service down")

    fake.get_news_sentiment = _boom
    monkeypatch.setitem(sys.modules, "integrations.news_sentiment", fake)

    sentiment, overview = load_news_sentiment(["AAPL"], "2026-04-15T10:30:00+00:00")
    assert sentiment == {} and overview is None


def test_apply_decisions_executes_pre_validated_actions():
    # Per-action validation now happens at the v2 boundary (validate_actions);
    # the backend receives only valid actions and reports execution results.
    backend = BacktestBackend.__new__(BacktestBackend)
    backend.run_id = "run_exec"

    class _StubSession:
        step_index = 1
        status = "waiting_decision"

        def submit_decisions(self, payload):
            executed = [{"action": a["action"], "symbol": a["symbol"],
                         "shares": a["position_size"]} for a in payload["actions"]]
            return {"accepted": True, "executed": executed,
                    "decision_source": "external_agent", "next_step": 1,
                    "status": "waiting_decision", "metrics": None}

    backend.session = _StubSession()
    ack = backend.apply_decisions([
        {"action": "buy", "symbol": "AAPL", "confidence": 0.7,
         "reasoning": "valid action here", "position_size": 3},
    ])
    SubmitAck.model_validate(ack)
    assert any(e["symbol"] == "AAPL" for e in ack["executed"])
    assert ack["rejected"] == []


def test_cancel_makes_context_report_closed(monkeypatch):
    symbols = ["AAPL", "MSFT", "JPM"]

    class _Loader:
        def fetch_bars(self, syms, start, end):
            return _synthetic_bars(symbols)

    monkeypatch.setattr(bb_mod.bha, "AlpacaDataLoader", lambda: _Loader())
    monkeypatch.setattr(bb_mod, "DJIA_30", symbols, raising=False)

    backend = BacktestBackend(
        run_id="run_closed_1", session_id="sess_c", agent_name="a",
        model_name="m", start_date="2026-04-15", end_date="2026-04-16",
    )
    backend.load_blocking()
    backend.cancel()

    ctx = backend.build_context()
    assert ctx["status"] == "closed"
    ContextEnvelope.model_validate(ctx)
