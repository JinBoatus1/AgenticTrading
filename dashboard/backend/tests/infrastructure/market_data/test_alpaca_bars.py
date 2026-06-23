"""Characterization tests for the extracted AlpacaDataLoader (Phase 2B1).

No real network/API calls: the Alpaca SDK client is replaced with a fake via
monkeypatch. Imports use the canonical package path.
"""

import json

import pandas as pd
import pytest

from alpaca.data.timeframe import TimeFrame

from dashboard.backend.infrastructure.market_data.alpaca_bars import AlpacaDataLoader
from dashboard.scripts import backtest_hourly_agent as bha

CLIENT_TARGET = "alpaca.data.historical.StockHistoricalDataClient"


def _bars_df(symbol_to_rows):
    """Build an Alpaca-style multi-index (symbol, timestamp) OHLCV dataframe."""
    frames = []
    for sym, rows in symbol_to_rows.items():
        idx = pd.MultiIndex.from_tuples(
            [(sym, pd.Timestamp(ts)) for ts, *_ in rows],
            names=["symbol", "timestamp"],
        )
        frame = pd.DataFrame(
            [
                {"open": o, "high": h, "low": l, "close": c, "volume": v}
                for _, o, h, l, c, v in rows
            ],
            index=idx,
        )
        frames.append(frame)
    return pd.concat(frames)


def _empty_bars_df():
    return pd.DataFrame(
        {"open": [], "high": [], "low": [], "close": [], "volume": []},
        index=pd.MultiIndex.from_arrays([[], []], names=["symbol", "timestamp"]),
    )


@pytest.fixture
def fake_alpaca(monkeypatch):
    """Patch the Alpaca client; returns a controllable state dict."""
    state = {"df": _empty_bars_df(), "exc": None, "requests": [], "ctor": []}

    class _FakeBars:
        def __init__(self, df):
            self.df = df

    class _FakeClient:
        def __init__(self, api_key, secret_key):
            state["ctor"].append((api_key, secret_key))

        def get_stock_bars(self, request):
            state["requests"].append(request)
            if state["exc"] is not None:
                raise state["exc"]
            return _FakeBars(state["df"])

    monkeypatch.setattr(CLIENT_TARGET, _FakeClient)
    return state


# --- compatibility / identity ----------------------------------------------

def test_old_script_exports_class():
    assert hasattr(bha, "AlpacaDataLoader")


def test_class_identity_between_paths():
    assert bha.AlpacaDataLoader is AlpacaDataLoader


# --- constructor -----------------------------------------------------------

def test_constructor_with_explicit_keys(fake_alpaca):
    loader = AlpacaDataLoader(api_key="explicit-k", secret_key="explicit-s")
    assert loader.api_key == "explicit-k"
    assert loader.secret_key == "explicit-s"
    assert loader.base_url == "https://data.alpaca.markets"
    # explicit keys -> credentials loader not used
    assert fake_alpaca["ctor"] == [("explicit-k", "explicit-s")]


def test_credentials_from_environment(fake_alpaca, monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "env-k")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "env-s")
    loader = AlpacaDataLoader()
    assert loader.api_key == "env-k"
    assert loader.secret_key == "env-s"


def test_environment_takes_precedence_over_file(fake_alpaca, monkeypatch, tmp_path):
    monkeypatch.setenv("ALPACA_API_KEY", "env-k")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "env-s")
    monkeypatch.setattr(
        "dashboard.backend.infrastructure.market_data.alpaca_bars.CREDENTIALS_DIR",
        tmp_path,
    )
    (tmp_path / "alpaca.json").write_text(
        json.dumps({"api_key": "file-k", "secret_key": "file-s"})
    )
    loader = AlpacaDataLoader()
    assert loader.api_key == "env-k"  # env wins over file


def test_credentials_from_file_fallback(fake_alpaca, monkeypatch, tmp_path):
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    monkeypatch.setattr(
        "dashboard.backend.infrastructure.market_data.alpaca_bars.CREDENTIALS_DIR",
        tmp_path,
    )
    (tmp_path / "alpaca.json").write_text(
        json.dumps({"api_key": "file-k", "secret_key": "file-s"})
    )
    loader = AlpacaDataLoader()
    assert loader.api_key == "file-k"
    assert loader.secret_key == "file-s"


def test_missing_credentials_exits(fake_alpaca, monkeypatch, tmp_path):
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    monkeypatch.setattr(
        "dashboard.backend.infrastructure.market_data.alpaca_bars.CREDENTIALS_DIR",
        tmp_path,  # no alpaca.json here
    )
    with pytest.raises(SystemExit):
        AlpacaDataLoader()


# --- fetch_bars ------------------------------------------------------------

def test_request_construction(fake_alpaca):
    loader = AlpacaDataLoader(api_key="k", secret_key="s")
    fake_alpaca["df"] = _bars_df({"AAPL": [("2026-01-02 10:00", 1, 2, 0.5, 1.5, 100)]})
    loader.fetch_bars(["AAPL"], "2026-01-01", "2026-01-03")
    req = fake_alpaca["requests"][0]
    assert req.symbol_or_symbols == ["AAPL"]
    assert req.timeframe.value == TimeFrame.Hour.value
    assert str(req.start).startswith("2026-01-01")
    assert str(req.end).startswith("2026-01-03")


def test_single_symbol_response_schema(fake_alpaca):
    loader = AlpacaDataLoader(api_key="k", secret_key="s")
    fake_alpaca["df"] = _bars_df(
        {
            "AAPL": [
                ("2026-01-02 10:00", 10, 11, 9, 10.5, 1000),
                ("2026-01-02 11:00", 10.5, 12, 10, 11.5, 1200),
            ]
        }
    )
    out = loader.fetch_bars(["AAPL"], "2026-01-01", "2026-01-03")
    assert set(out.keys()) == {"AAPL"}
    df = out["AAPL"]
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert df.index.name == "timestamp"
    assert isinstance(df.index, pd.DatetimeIndex)
    assert len(df) == 2


def test_multi_symbol_response(fake_alpaca):
    loader = AlpacaDataLoader(api_key="k", secret_key="s")
    fake_alpaca["df"] = _bars_df(
        {
            "AAPL": [("2026-01-02 10:00", 10, 11, 9, 10.5, 1000)],
            "MSFT": [("2026-01-02 10:00", 20, 21, 19, 20.5, 2000)],
        }
    )
    out = loader.fetch_bars(["AAPL", "MSFT"], "2026-01-01", "2026-01-03")
    assert set(out.keys()) == {"AAPL", "MSFT"}
    assert out["MSFT"]["close"].iloc[0] == 20.5


def test_missing_symbol_skipped(fake_alpaca):
    loader = AlpacaDataLoader(api_key="k", secret_key="s")
    fake_alpaca["df"] = _bars_df({"AAPL": [("2026-01-02 10:00", 10, 11, 9, 10.5, 1000)]})
    out = loader.fetch_bars(["AAPL", "TSLA"], "2026-01-01", "2026-01-03")
    assert set(out.keys()) == {"AAPL"}  # TSLA absent -> skipped


def test_empty_response_returns_empty_dict(fake_alpaca):
    loader = AlpacaDataLoader(api_key="k", secret_key="s")
    fake_alpaca["df"] = _empty_bars_df()
    out = loader.fetch_bars(["AAPL"], "2026-01-01", "2026-01-03")
    assert out == {}


def test_results_sorted_by_timestamp(fake_alpaca):
    loader = AlpacaDataLoader(api_key="k", secret_key="s")
    fake_alpaca["df"] = _bars_df(
        {
            "AAPL": [
                ("2026-01-02 13:00", 13, 14, 12, 13.5, 1300),
                ("2026-01-02 10:00", 10, 11, 9, 10.5, 1000),
                ("2026-01-02 11:00", 11, 12, 10, 11.5, 1100),
            ]
        }
    )
    out = loader.fetch_bars(["AAPL"], "2026-01-01", "2026-01-03")
    idx = out["AAPL"].index
    assert list(idx) == sorted(idx)


def test_timezone_preserved(fake_alpaca):
    loader = AlpacaDataLoader(api_key="k", secret_key="s")
    fake_alpaca["df"] = _bars_df(
        {"AAPL": [(pd.Timestamp("2026-01-02 10:00", tz="UTC"), 10, 11, 9, 10.5, 1000)]}
    )
    out = loader.fetch_bars(["AAPL"], "2026-01-01", "2026-01-03")
    assert out["AAPL"].index.tz is not None
    assert str(out["AAPL"].index.tz) == "UTC"


def test_timezone_naive_preserved(fake_alpaca):
    loader = AlpacaDataLoader(api_key="k", secret_key="s")
    fake_alpaca["df"] = _bars_df({"AAPL": [("2026-01-02 10:00", 10, 11, 9, 10.5, 1000)]})
    out = loader.fetch_bars(["AAPL"], "2026-01-01", "2026-01-03")
    assert out["AAPL"].index.tz is None


def test_exception_is_caught_and_returns_empty(fake_alpaca):
    loader = AlpacaDataLoader(api_key="k", secret_key="s")
    fake_alpaca["exc"] = RuntimeError("boom")
    out = loader.fetch_bars(["AAPL"], "2026-01-01", "2026-01-03")
    assert out == {}
