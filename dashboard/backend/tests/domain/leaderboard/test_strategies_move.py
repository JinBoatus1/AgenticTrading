"""Phase 3C3 — leaderboard strategies move + registration characterization.

Verifies the baseline strategy package moved to the canonical
``dashboard.backend.domain.leaderboard.strategies`` package while the old
``engines.strategies`` modules remain re-export shims with identical class
identity, and characterizes registry lookup, aliases, and unknown-strategy
behavior.
"""

import pytest

from dashboard.backend.domain.leaderboard import strategies as canon
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
# Old-path identity (shims re-export the same classes)
# ---------------------------------------------------------------------------

def test_strategies_shim_reexports_identical_classes():
    from dashboard.backend.engines.strategies import (
        BaselineStrategy as ShimBase,
        available_strategies as shim_available,
        get_strategy as shim_get,
    )
    from dashboard.backend.engines.strategies.buy_hold import BuyHoldStrategy as ShimBuyHold
    from dashboard.backend.engines.strategies.llm_agent import LLMAgentStrategy as ShimLLM

    assert ShimBase is BaselineStrategy
    assert shim_get is canon.get_strategy
    assert shim_available is canon.available_strategies
    assert ShimBuyHold is BuyHoldStrategy
    assert ShimLLM is LLMAgentStrategy


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
