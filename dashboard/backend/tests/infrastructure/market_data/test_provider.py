"""Market-data provider boundary and feature-gate tests."""

from __future__ import annotations

import subprocess
import sys

import pytest


def test_provider_module_import_does_not_import_vnpy():
    code = (
        "import sys\n"
        "import dashboard.backend.infrastructure.market_data.provider\n"
        "assert not any(name == 'vnpy' or name.startswith('vnpy.') "
        "for name in sys.modules)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_alpaca_is_the_default_provider(monkeypatch):
    from dashboard.backend.infrastructure.market_data import provider

    class FakeAlpacaLoader:
        pass

    monkeypatch.setattr(provider, "AlpacaDataLoader", FakeAlpacaLoader)

    created = provider.create_market_data_provider(provider.ALPACA)

    assert isinstance(created, FakeAlpacaLoader)


@pytest.mark.parametrize("value", ["1", "true", "TRUE", " yes ", "on"])
def test_vnpy_simulation_truthy_feature_values(monkeypatch, value):
    from dashboard.backend.infrastructure.market_data import provider

    monkeypatch.setenv("ENABLE_VNPY_SIMULATION", value)

    assert provider.vnpy_simulation_enabled() is True


@pytest.mark.parametrize("value", ["", "0", "false", "no", "disabled"])
def test_vnpy_simulation_falsey_feature_values(monkeypatch, value):
    from dashboard.backend.infrastructure.market_data import provider

    monkeypatch.setenv("ENABLE_VNPY_SIMULATION", value)

    assert provider.vnpy_simulation_enabled() is False


def test_unknown_data_source_is_rejected():
    from dashboard.backend.infrastructure.market_data import provider

    with pytest.raises(provider.UnsupportedMarketDataSource, match="unknown"):
        provider.validate_market_data_source("unknown")


def test_disabled_vnpy_simulation_is_rejected(monkeypatch):
    from dashboard.backend.infrastructure.market_data import provider

    monkeypatch.delenv("ENABLE_VNPY_SIMULATION", raising=False)

    with pytest.raises(provider.MarketDataSourceDisabled, match="disabled"):
        provider.validate_market_data_source(provider.VNPY_SIMULATION)
