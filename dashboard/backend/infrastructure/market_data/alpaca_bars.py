"""Alpaca historical bar loader.

Extracted (Phase 2B1) from ``AlpacaDataLoader`` in
``dashboard/scripts/backtest_hourly_agent.py``. One deliberate behavior change
since the move (B0/H4 deep fix): missing credentials or a missing alpaca-py SDK
raise :class:`MarketDataUnavailableError` instead of ``sys.exit(1)``. SystemExit
is a BaseException — it sailed past ``except Exception`` at every server call
site, silently killed daemon loader threads, and wedged the ASGI loop (the
original B0 hang). A plain exception is catchable everywhere; only CLI
entrypoints translate it back into an exit code.

This is intentionally NOT merged with ``dashboard/backend/market_data.py``; that
consolidation belongs to a later domain-migration phase. The Alpaca SDK imports
remain lazy (inside ``__init__``) so importing this module performs no network
requests.
"""

import json
import os
from typing import Dict, List, Optional

import pandas as pd

from dashboard.backend.paths import CREDENTIALS_DIR


class MarketDataUnavailableError(RuntimeError):
    """Market data cannot be loaded (missing credentials, SDK, or data).

    Deliberately a plain Exception subclass: server code catches it with
    ``except Exception``; CLI entrypoints convert it to ``sys.exit(1)``.
    """


class AlpacaCredentialsError(MarketDataUnavailableError):
    """Raised when Alpaca API credentials are not configured."""


class AlpacaDataLoader:
    """Fetches historical hourly bars from Alpaca API."""

    def __init__(self, api_key: Optional[str] = None, secret_key: Optional[str] = None):
        """Initialize with Alpaca credentials."""
        if not api_key or not secret_key:
            creds = self._load_credentials()
            api_key = creds.get("api_key")
            secret_key = creds.get("secret_key")

        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = "https://data.alpaca.markets"

        try:
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.data.requests import StockBarsRequest
            from alpaca.data.timeframe import TimeFrame

            self.client = StockHistoricalDataClient(self.api_key, self.secret_key)
            self.StockBarsRequest = StockBarsRequest
            self.TimeFrame = TimeFrame
            print("✅ Alpaca credentials loaded")
        except ImportError as e:
            print(f"❌ alpaca-py not installed: {e}")
            print("   Run: pip install alpaca-py")
            raise MarketDataUnavailableError(
                "alpaca-py is not installed (pip install alpaca-py)"
            ) from e

    def _load_credentials(self) -> Dict:
        """Load Alpaca credentials from environment variables or file."""
        # Try environment variables first (for Render, Docker, etc.)
        api_key = os.getenv('ALPACA_API_KEY')
        secret_key = os.getenv('ALPACA_SECRET_KEY')

        if api_key and secret_key:
            print("✅ Loaded Alpaca credentials from environment variables")
            return {"api_key": api_key, "secret_key": secret_key}

        # Fall back to credentials file (for local development)
        creds_path = CREDENTIALS_DIR / "alpaca.json"
        if not creds_path.exists():
            print(f"❌ Credentials not found in environment variables or file: {creds_path}")
            print("   Set ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables")
            raise AlpacaCredentialsError(
                "Alpaca credentials not found (set ALPACA_API_KEY and "
                f"ALPACA_SECRET_KEY, or provide {creds_path})"
            )

        print(f"✅ Loaded Alpaca credentials from {creds_path}")
        with open(creds_path) as f:
            return json.load(f)

    def fetch_bars(self, symbols: List[str], start: str, end: str) -> Dict[str, pd.DataFrame]:
        """
        Fetch hourly OHLCV data from Alpaca API.

        Args:
            symbols: List of stock symbols
            start: Start date (YYYY-MM-DD)
            end: End date (YYYY-MM-DD)

        Returns:
            {symbol: DataFrame with timestamp, open, high, low, close, volume}
        """
        if not self.client:
            print("⚠️ Alpaca not configured — skipping bar fetch")
            return {}

        print(f"\n📊 Fetching {len(symbols)} symbols from {start} to {end}...")
        print(f"   Timeframe: Hourly (1h) with forward-filled price cache\n")

        request = self.StockBarsRequest(
            symbol_or_symbols=symbols,
            timeframe=self.TimeFrame.Hour,
            start=start,
            end=end,
        )

        try:
            bars = self.client.get_stock_bars(request)

            # Convert to DataFrame per symbol
            data = {}
            for symbol in symbols:
                if symbol in bars.df.index.get_level_values(0):
                    df = bars.df.xs(symbol).reset_index()

                    # Extract OHLCV columns
                    df = df[["timestamp", "open", "high", "low", "close", "volume"]].copy()
                    df["timestamp"] = pd.to_datetime(df["timestamp"])
                    df.set_index("timestamp", inplace=True)
                    data[symbol] = df.sort_index()
                    print(f"  ✅ {symbol}: {len(df)} hourly bars")
                else:
                    print(f"  ⚠️  {symbol}: No data available")

            return data

        except Exception as e:
            print(f"❌ Error fetching bars: {e}")
            import traceback
            traceback.print_exc()
            return {}
