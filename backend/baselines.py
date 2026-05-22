"""
Baseline calculations for paper trading comparison.
Generates benchmark equity curves for comparison:
- DJIA Index (^DJI)
- Buy-and-Hold (equal-weighted DJIA stocks)
"""

import json
import requests
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass


DJIA_SYMBOLS = [
    "AAPL", "MSFT", "JPM", "V", "JNJ",
    "WMT", "PG", "UNH", "NVDA", "HD",
    "KO", "IBM", "MCD", "CAT", "AXP",
    "GS", "BA", "MMM", "AMGN", "INTC",
    "VZ", "PFE", "MRK", "HON", "CSCO",
    "NFLX", "TSLA", "CRM", "TRV", "DIS"
]


class BaselineCalculator:
    """Calculate baseline equity curves for benchmarking."""
    
    def __init__(self, api_key: Optional[str] = None, 
                 secret_key: Optional[str] = None):
        """Initialize with Alpaca credentials."""
        if api_key is None:
            self._load_credentials()
        else:
            self.api_key = api_key
            self.secret_key = secret_key
        
        self.base_url = "https://paper-api.alpaca.markets"
        self.data_api_url = "https://data.alpaca.markets"
        self.headers = {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key,
        }
    
    def _load_credentials(self):
        """Load credentials from credentials/alpaca.json"""
        creds_path = Path(__file__).parent.parent / "credentials" / "alpaca.json"
        
        if creds_path.exists():
            with open(creds_path, 'r') as f:
                creds = json.load(f)
                self.api_key = creds.get('api_key') or creds.get('apiKey')
                self.secret_key = creds.get('secret_key') or creds.get('secretKey')
        else:
            raise FileNotFoundError(f"Credentials file not found: {creds_path}")
    
    def get_djia_historical(self, days: int = 31) -> Optional[List[Dict]]:
        """
        Get DJIA (^DJI) historical prices.
        
        Args:
            days: Number of days of history to fetch
        
        Returns:
            List of {timestamp, price, equity} points (normalized to $100k starting equity)
        """
        try:
            # Calculate date range
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            # Fetch DJIA bars
            url = f"{self.data_api_url}/v2/stocks/DJIA/bars"
            params = {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "timeframe": "1D"
            }
            
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            
            if response.status_code != 200:
                print(f"Error fetching DJIA: {response.status_code}")
                return None
            
            data = response.json()
            bars = data.get("bars", [])
            
            if not bars:
                return None
            
            # Convert to equity curve (normalize to $100k)
            initial_price = bars[0]["c"]  # Close
            equity_curve = []
            
            for bar in bars:
                price = bar["c"]
                # Calculate equity assuming $100k invested at initial price
                equity = 100000 * (price / initial_price)
                
                equity_curve.append({
                    "timestamp": bar["t"],
                    "price": price,
                    "equity": equity,
                    "daily_return": (price - initial_price) / initial_price
                })
            
            return equity_curve
        
        except Exception as e:
            print(f"Exception in get_djia_historical: {e}")
            return None
    
    def get_djia_symbol(self, symbol: str = "^GSPC") -> Optional[str]:
        """
        Map DJIA to actual ticker symbol.
        Note: Alpaca doesn't directly support ^DJI, so we'll use S&P 500 (^GSPC) or simulate.
        
        Returns actual ticker to use for fetching.
        """
        # Most reliable: use SPY (S&P 500 ETF) as proxy or use an actual DJIA symbol
        return "SPY"  # S&P 500 ETF (close proxy to DJIA)
    
    def get_buy_and_hold_djia(self, days: int = 31) -> Optional[List[Dict]]:
        """
        Calculate Buy-and-Hold returns for equal-weighted DJIA stocks.
        
        Args:
            days: Number of days of history
        
        Returns:
            List of {timestamp, equity, daily_return} points
        """
        try:
            # Get price bars for first few DJIA stocks (faster than all 30)
            sample_symbols = DJIA_SYMBOLS[:10]  # Use first 10 for speed
            
            # Fetch historical bars for each
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            all_prices = {}
            
            for symbol in sample_symbols:
                try:
                    url = f"{self.data_api_url}/v2/stocks/{symbol}/bars"
                    params = {
                        "start": start_date.isoformat(),
                        "end": end_date.isoformat(),
                        "timeframe": "1D"
                    }
                    
                    response = requests.get(url, headers=self.headers, params=params, timeout=5)
                    
                    if response.status_code == 200:
                        data = response.json()
                        bars = data.get("bars", [])
                        if bars:
                            all_prices[symbol] = bars
                except Exception as e:
                    print(f"Error fetching {symbol}: {e}")
                    continue
            
            if not all_prices:
                return None
            
            # Build equal-weighted portfolio
            equity_curve = []
            
            # Get all timestamps (assume same for all symbols)
            first_symbol = next(iter(all_prices.keys()))
            timestamps = [bar["t"] for bar in all_prices[first_symbol]]
            
            for bar_idx, timestamp in enumerate(timestamps):
                # Calculate equal-weighted return
                total_return = 0
                count = 0
                
                for symbol in all_prices:
                    bars = all_prices[symbol]
                    if bar_idx < len(bars):
                        bar = bars[bar_idx]
                        price = bar["c"]
                        
                        if bar_idx == 0:
                            initial_price = price
                            daily_return = 0
                        else:
                            initial_price = all_prices[symbol][0]["c"]
                            daily_return = (price / initial_price) - 1
                        
                        total_return += daily_return
                        count += 1
                
                # Average return across symbols
                avg_return = total_return / count if count > 0 else 0
                
                # Calculate equity (starting with $100k)
                equity = 100000 * (1 + avg_return)
                
                equity_curve.append({
                    "timestamp": timestamp,
                    "equity": equity,
                    "daily_return": avg_return
                })
            
            return equity_curve
        
        except Exception as e:
            print(f"Exception in get_buy_and_hold_djia: {e}")
            return None
    
    def generate_synthetic_baselines(self, days: int = 31) -> Dict[str, List[Dict]]:
        """
        Generate synthetic baseline equity curves (for testing if real data unavailable).
        
        Returns:
            Dict with 'djia' and 'buy_and_hold' equity curves
        """
        import random
        
        baselines = {}
        
        # Generate DJIA synthetic data
        djia_curve = []
        djia_equity = 100000
        
        for i in range(days):
            # DJIA drift: ~0.04% per day, volatility ~1.2%
            drift = 0.0004
            volatility = 0.012
            daily_return = drift + volatility * random.gauss(0, 1)
            djia_equity *= (1 + daily_return)
            
            timestamp = (datetime.now() - timedelta(days=days-i)).isoformat()
            djia_curve.append({
                "timestamp": timestamp,
                "equity": djia_equity,
                "daily_return": daily_return
            })
        
        baselines["djia"] = djia_curve
        
        # Generate Buy-and-Hold synthetic data
        bah_curve = []
        bah_equity = 100000
        
        for i in range(days):
            # B&H drift: ~0.03% per day, volatility ~1.5%
            drift = 0.0003
            volatility = 0.015
            daily_return = drift + volatility * random.gauss(0, 1)
            bah_equity *= (1 + daily_return)
            
            timestamp = (datetime.now() - timedelta(days=days-i)).isoformat()
            bah_curve.append({
                "timestamp": timestamp,
                "equity": bah_equity,
                "daily_return": daily_return
            })
        
        baselines["buy_and_hold"] = bah_curve
        
        return baselines
    
    def get_baselines(self, days: int = 31, use_synthetic: bool = False) -> Dict[str, List[Dict]]:
        """
        Get all baseline equity curves.
        
        Args:
            days: Days of history to fetch
            use_synthetic: If True, generate synthetic data (for testing)
        
        Returns:
            Dict with 'djia' and 'buy_and_hold' equity curves
        """
        baselines = {}
        
        # Try to fetch real data
        if not use_synthetic:
            djia_data = self.get_djia_historical(days=days)
            if djia_data:
                baselines["djia"] = djia_data
            
            bah_data = self.get_buy_and_hold_djia(days=days)
            if bah_data:
                baselines["buy_and_hold"] = bah_data
        
        # Fall back to synthetic if real data not available
        if not baselines or use_synthetic:
            synthetic = self.generate_synthetic_baselines(days=days)
            baselines.update(synthetic)
        
        return baselines


def get_baselines(days: int = 31, use_synthetic: bool = False) -> Dict[str, List[Dict]]:
    """
    Convenience function to get baseline equity curves.
    
    Usage:
        baselines = get_baselines(days=31)
        # baselines['djia'] = [{timestamp, equity, daily_return}, ...]
        # baselines['buy_and_hold'] = [{...}, ...]
    """
    try:
        calculator = BaselineCalculator()
        return calculator.get_baselines(days=days, use_synthetic=use_synthetic)
    except Exception as e:
        print(f"Error getting baselines: {e}")
        # Return synthetic as fallback
        calculator = BaselineCalculator.__new__(BaselineCalculator)
        return calculator.generate_synthetic_baselines(days=31)
