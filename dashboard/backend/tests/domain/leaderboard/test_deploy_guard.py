"""H6 — leaderboard must not publish a rule-based fallback under an LLM name.

``deploy_model_run`` refuses to persist an LLM entry that silently fell back to
rule-based trading (no client, or a model id the gateway rejected so every call
failed), unless ``allow_fallback=True``. Rule-based baselines (which expose no
``used_llm``) are unaffected.
"""

import pytest

from dashboard.backend.database import BacktestDatabase
from dashboard.backend.domain.leaderboard import service as canon_service


_CONFIG = {
    "session_id": "lb-guard-test",
    "start_date": "2026-04-15",
    "end_date": "2026-05-15",
    "initial_capital": 100000,
    "strategies": [
        {"id": "claude_haiku_4_5", "name": "Haiku", "model": "Claude Haiku",
         "strategy": "llm_agent", "model_id": "test-model"},
        {"id": "djia_index", "name": "DJIA", "model": "DJIA", "strategy": "market_index"},
    ],
}


class FakeLLMStrategy:
    """Mimics LLMAgentStrategy's reporting surface (exposes ``used_llm``).

    ``decision_steps`` is the number of decision points in the run; when omitted
    it defaults to ``llm_calls`` (i.e. 100% LLM coverage), so existing tests that
    only care about the used_llm/llm_calls axis stay at full coverage.
    """

    def __init__(self, *, used_llm, llm_calls, decision_steps=None, model_id="test-model"):
        self.used_llm = used_llm
        self.llm_calls = llm_calls
        self.decision_steps = llm_calls if decision_steps is None else decision_steps
        self.input_tokens = 10
        self.output_tokens = 5
        self.model_id = model_id

    def required_symbols(self):
        return ["AAPL"]

    def run(self, bars, start, end, capital):
        return [{"timestamp": "2026-04-15T14:00:00", "equity": capital,
                 "cash": 0, "positions_value": capital}]

    def num_trades(self):
        return 0


class FakeBaseline:
    """A rule-based baseline: intentionally exposes NO ``used_llm`` attribute."""

    def __init__(self):
        self.llm_calls = 0
        self.model_id = None
        self.input_tokens = 0
        self.output_tokens = 0

    def required_symbols(self):
        return ["AAPL"]

    def run(self, bars, start, end, capital):
        return [{"timestamp": "2026-04-15T14:00:00", "equity": capital,
                 "cash": 0, "positions_value": capital}]

    def num_trades(self):
        return 0


@pytest.fixture
def guard_env(tmp_path, monkeypatch):
    test_db = BacktestDatabase(db_path=tmp_path / "lb.db")
    monkeypatch.setattr(canon_service, "db", test_db)
    monkeypatch.setattr(canon_service, "load_leaderboard_config", lambda: dict(_CONFIG))
    monkeypatch.setattr(canon_service, "fetch_hourly_bars", lambda syms, s, e: {"AAPL": object()})
    monkeypatch.setattr(canon_service, "calc_metrics", lambda curve, cap: {
        "initial_equity": cap, "final_equity": cap, "total_return": 0.0,
        "sharpe_ratio": 0.0, "max_drawdown": 0.0,
    })
    monkeypatch.setattr(canon_service.token_cost, "estimate_cost_usd", lambda m, i, o: 0.0)
    return test_db


def _use(monkeypatch, impl):
    monkeypatch.setattr(canon_service, "get_strategy", lambda entry: impl)


def test_refuses_when_used_llm_false(guard_env, monkeypatch):
    _use(monkeypatch, FakeLLMStrategy(used_llm=False, llm_calls=0))
    with pytest.raises(canon_service.LeaderboardFallbackError):
        canon_service.deploy_model_run("claude_haiku_4_5", force_refresh=True)
    run_id = canon_service._run_id("claude_haiku_4_5", "2026-04-15", "2026-05-15")
    assert guard_env.get_run(run_id) is None  # nothing persisted


def test_refuses_when_llm_calls_zero(guard_env, monkeypatch):
    # Client existed (used_llm True) but every call failed → 0 real LLM calls.
    _use(monkeypatch, FakeLLMStrategy(used_llm=True, llm_calls=0))
    with pytest.raises(canon_service.LeaderboardFallbackError):
        canon_service.deploy_model_run("claude_haiku_4_5", force_refresh=True)


def test_refuses_partial_llm_fallback(guard_env, monkeypatch):
    # The client worked for one step then every other step fell back to
    # rule-based: 1 of 161 decisions came from the model. Publishing this curve
    # under the model's name would be ~99% rule-based. (This is the real Qwen
    # 1-of-161 run that silently topped the board.)
    _use(monkeypatch, FakeLLMStrategy(used_llm=True, llm_calls=1, decision_steps=161))
    with pytest.raises(canon_service.LeaderboardFallbackError):
        canon_service.deploy_model_run("claude_haiku_4_5", force_refresh=True)
    run_id = canon_service._run_id("claude_haiku_4_5", "2026-04-15", "2026-05-15")
    assert guard_env.get_run(run_id) is None  # nothing persisted


def test_refuses_just_below_coverage_threshold(guard_env, monkeypatch):
    # 94 of 100 steps LLM-decided = 94% < 95% threshold → refuse.
    _use(monkeypatch, FakeLLMStrategy(used_llm=True, llm_calls=94, decision_steps=100))
    with pytest.raises(canon_service.LeaderboardFallbackError):
        canon_service.deploy_model_run("claude_haiku_4_5", force_refresh=True)


def test_publishes_at_coverage_threshold(guard_env, monkeypatch):
    # 95 of 100 steps LLM-decided = exactly 95% → allowed (transient API blips
    # on a genuine LLM run must not be misread as a fallback curve).
    _use(monkeypatch, FakeLLMStrategy(used_llm=True, llm_calls=95, decision_steps=100))
    result = canon_service.deploy_model_run("claude_haiku_4_5", force_refresh=True)
    assert guard_env.get_run(result["run_id"]) is not None


def test_allow_fallback_publishes(guard_env, monkeypatch):
    _use(monkeypatch, FakeLLMStrategy(used_llm=False, llm_calls=0))
    result = canon_service.deploy_model_run(
        "claude_haiku_4_5", force_refresh=True, allow_fallback=True
    )
    assert guard_env.get_run(result["run_id"]) is not None


def test_publishes_real_llm_run(guard_env, monkeypatch):
    _use(monkeypatch, FakeLLMStrategy(used_llm=True, llm_calls=5))
    result = canon_service.deploy_model_run("claude_haiku_4_5", force_refresh=True)
    assert result["llm_calls"] == 5
    assert guard_env.get_run(result["run_id"]) is not None


def test_baseline_without_used_llm_publishes(guard_env, monkeypatch):
    # A rule-based baseline legitimately makes 0 LLM calls and must NOT be blocked.
    _use(monkeypatch, FakeBaseline())
    result = canon_service.deploy_model_run("djia_index", force_refresh=True)
    assert guard_env.get_run(result["run_id"]) is not None


def test_ensure_leaderboard_runs_also_guards_llm_fallback(tmp_path, monkeypatch):
    """Belt-and-suspenders: a misconfigured LLM entry left on the auto-compute
    path (auto_compute true) is still refused, not silently published."""
    cfg = {
        "session_id": "lb-auto-test",
        "start_date": "2026-04-15",
        "end_date": "2026-05-15",
        "initial_capital": 100000,
        "strategies": [
            {"id": "sneaky_llm", "name": "Sneaky", "model": "Sneaky",
             "strategy": "llm_agent", "auto_compute": True},
        ],
    }
    test_db = BacktestDatabase(db_path=tmp_path / "lb.db")
    monkeypatch.setattr(canon_service, "db", test_db)
    monkeypatch.setattr(canon_service, "load_leaderboard_config", lambda: dict(cfg))
    monkeypatch.setattr(canon_service, "get_strategy", lambda entry: FakeLLMStrategy(used_llm=False, llm_calls=0))
    monkeypatch.setattr(canon_service, "fetch_hourly_bars", lambda syms, s, e: {"AAPL": object()})
    monkeypatch.setattr(canon_service, "calc_metrics", lambda curve, cap: {
        "initial_equity": cap, "final_equity": cap, "total_return": 0.0,
        "sharpe_ratio": 0.0, "max_drawdown": 0.0,
    })
    with pytest.raises(canon_service.LeaderboardFallbackError):
        canon_service.ensure_leaderboard_runs(force_refresh=True)


def test_default_model_name_is_gateway_aware(monkeypatch):
    """The gateway-aware default llm_agent.py now uses: native id without a
    CommonStack key, the CommonStack slug with one."""
    from dashboard.backend.infrastructure.llm import backtest_harness as bh

    monkeypatch.delenv("COMMONSTACK_API_KEY", raising=False)
    assert bh.default_model_name() == bh.LLM_MODEL_NAME

    monkeypatch.setenv("COMMONSTACK_API_KEY", "x")
    assert bh.default_model_name() == bh.COMMONSTACK_MODEL_NAME
