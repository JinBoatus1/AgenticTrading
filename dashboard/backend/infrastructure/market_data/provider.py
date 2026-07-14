"""Market-data provider contract, selection, and feature gating."""

from __future__ import annotations

import importlib.util
import os
from typing import Protocol

import pandas as pd

from .alpaca_bars import AlpacaDataLoader


ALPACA = "alpaca"
VNPY_SIMULATION = "vnpy_simulation"
SUPPORTED_DATA_SOURCES = (ALPACA, VNPY_SIMULATION)

_TRUTHY = {"1", "true", "yes", "on"}


class MarketDataProvider(Protocol):
    """Normalized hourly market-data input consumed by backtests."""

    def fetch_bars(
        self,
        symbols: list[str],
        start: str,
        end: str,
    ) -> dict[str, pd.DataFrame]:
        """Return symbol-keyed OHLCV frames for the requested date window."""


class UnsupportedMarketDataSource(ValueError):
    """Raised when a request names a data source outside the allow-list."""


class MarketDataSourceDisabled(RuntimeError):
    """Raised when a known data source is disabled by configuration."""


class MarketDataDependencyError(RuntimeError):
    """Raised when an optional provider dependency is not installed."""


def vnpy_simulation_enabled() -> bool:
    """Return whether the development-only vn.py simulator is enabled."""
    value = os.getenv("ENABLE_VNPY_SIMULATION", "")
    return value.strip().lower() in _TRUTHY


def validate_market_data_source(data_source: str) -> None:
    """Validate the source name and feature gate without creating a client."""
    if data_source not in SUPPORTED_DATA_SOURCES:
        raise UnsupportedMarketDataSource(
            f"Unknown market data source: {data_source!r}"
        )
    if data_source == VNPY_SIMULATION and not vnpy_simulation_enabled():
        raise MarketDataSourceDisabled(
            "vn.py simulation is disabled; set ENABLE_VNPY_SIMULATION=true"
        )


def ensure_market_data_source_available(data_source: str) -> None:
    """Validate configuration and optional dependencies without importing vn.py."""
    validate_market_data_source(data_source)
    if data_source == VNPY_SIMULATION and importlib.util.find_spec("vnpy") is None:
        raise MarketDataDependencyError(
            "vn.py is not installed; run pip install -r requirements-vnpy.txt"
        )


def create_market_data_provider(data_source: str = ALPACA) -> MarketDataProvider:
    """Create a provider while keeping optional vn.py imports isolated."""
    ensure_market_data_source_available(data_source)

    if data_source == ALPACA:
        return AlpacaDataLoader()

    try:
        from .vnpy_simulation import VnpySimulationProvider
    except ModuleNotFoundError as exc:
        if exc.name == "vnpy" or (exc.name and exc.name.startswith("vnpy.")):
            raise MarketDataDependencyError(
                "vn.py is not installed; run "
                "pip install -r requirements-vnpy.txt"
            ) from exc
        raise

    return VnpySimulationProvider()
