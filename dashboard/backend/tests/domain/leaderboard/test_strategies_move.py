"""Phase 3C3 — leaderboard strategies registration characterization.

Verifies the canonical ``dashboard.backend.domain.leaderboard.strategies``
package and characterizes registry lookup, aliases, and unknown-strategy
behavior.
"""

import json

import pytest

from dashboard.backend.paths import CONFIG_DIR
from dashboard.backend.domain.leaderboard import strategies as canon
from dashboard.backend.domain.leaderboard.strategies import (
    llm_agent as llm_agent_module,
)
from dashboard.backend.domain.leaderboard.strategies.base import BaselineStrategy
from dashboard.backend.domain.leaderboard.strategies.buy_hold import BuyHoldStrategy
from dashboard.backend.domain.leaderboard.strategies.equal_weight_buyhold import (
    EqualWeightBuyHoldStrategy,
)
from dashboard.backend.domain.leaderboard.strategies.equal_weight_index import (
    EqualWeightIndexStrategy,
)
from dashboard.backend.domain.leaderboard.strategies.llm_agent import LLMAgentStrategy
from dashboard.backend.domain.leaderboard.strategies.market_index import MarketIndexStrategy
from dashboard.backend.domain.leaderboard.strategies.mean_variance import MeanVarianceStrategy


_EXPECTED_KEYS = {
    "buy_hold",
    "equal_weight_index",
    "equal_weight_buyhold",
    "market_index",
    "mean_variance",
    "llm_agent",
}


# ---------------------------------------------------------------------------
# Registry class identity
# ---------------------------------------------------------------------------

def test_registry_module_identity_single_class_objects():
    # The registry must resolve to the SAME class objects exposed by submodules.
    registry = canon.available_strategies()
    assert registry["buy_hold"] is BuyHoldStrategy
    assert registry["equal_weight_index"] is EqualWeightIndexStrategy
    assert registry["equal_weight_buyhold"] is EqualWeightBuyHoldStrategy
    assert registry["market_index"] is MarketIndexStrategy
    assert registry["mean_variance"] is MeanVarianceStrategy
    assert registry["llm_agent"] is LLMAgentStrategy


# ---------------------------------------------------------------------------
# Registration + lookup
# ---------------------------------------------------------------------------

def test_available_strategies_keys():
    assert set(canon.available_strategies().keys()) == _EXPECTED_KEYS


def test_get_strategy_resolves_by_strategy_key():
    strat = canon.get_strategy({"id": "x", "name": "X", "strategy": "mean_variance"})
    assert isinstance(strat, MeanVarianceStrategy)
    assert strat.id == "x"
    assert strat.name == "X"


def test_get_strategy_supports_type_aliases():
    # Legacy config ``type`` values still resolve via the alias table.
    assert isinstance(canon.get_strategy({"type": "index"}), EqualWeightIndexStrategy)
    assert isinstance(canon.get_strategy({"type": "buy_hold"}), BuyHoldStrategy)


def test_get_strategy_unknown_raises_value_error():
    with pytest.raises(ValueError, match="Unknown baseline strategy"):
        canon.get_strategy({"strategy": "does_not_exist"})


def test_required_symbols_defaults_and_overrides():
    # equal_weight_index defaults to DJIA 30, honors explicit symbols.
    default = EqualWeightIndexStrategy({}).required_symbols()
    assert len(default) == 30
    custom = EqualWeightIndexStrategy({"symbols": ["AAPL", "MSFT"]}).required_symbols()
    assert custom == ["AAPL", "MSFT"]
    # market_index excludes ^-prefixed index symbols from the Alpaca fetch.
    assert MarketIndexStrategy({"symbols": ["^DJI"]}).required_symbols() == []


def test_llm_agent_passes_model_reasoning_to_client_factory(monkeypatch):
    captured = {}
    expected_client = object()

    def _fake_factory(integration=None, *, reasoning_effort=None):
        captured["integration"] = integration
        captured["reasoning_effort"] = reasoning_effort
        return expected_client

    monkeypatch.setattr(llm_agent_module, "HAS_ANTHROPIC", True)
    monkeypatch.setattr(llm_agent_module, "make_llm_client", _fake_factory)

    strategy = LLMAgentStrategy(
        {
            "integration": "openrouter",
            "reasoning_effort": "none",
        }
    )

    assert strategy.reasoning_effort == "none"
    assert strategy._make_client() is expected_client
    assert captured == {
        "integration": "openrouter",
        "reasoning_effort": "none",
    }


def test_llm_agent_without_reasoning_keeps_legacy_factory_behavior(monkeypatch):
    captured = {}

    def _fake_factory(integration=None, *, reasoning_effort=None):
        captured["integration"] = integration
        captured["reasoning_effort"] = reasoning_effort
        return object()

    monkeypatch.setattr(llm_agent_module, "HAS_ANTHROPIC", True)
    monkeypatch.setattr(llm_agent_module, "make_llm_client", _fake_factory)

    strategy = LLMAgentStrategy({"integration": "commonstack"})
    strategy._make_client()

    assert strategy.reasoning_effort is None
    assert captured == {
        "integration": "commonstack",
        "reasoning_effort": None,
    }


def test_only_nemotron_leaderboard_entry_disables_reasoning():
    config = json.loads((CONFIG_DIR / "leaderboard.json").read_text(encoding="utf-8"))
    strategies = config["strategies"]
    nemotron = next(s for s in strategies if s["id"] == "nemotron_3_nano_30b")

    assert nemotron["reasoning_effort"] == "none"
    assert all(
        "reasoning_effort" not in strategy
        for strategy in strategies
        if strategy["id"] != "nemotron_3_nano_30b"
    )
