"""
Baseline data fetcher - uses real historical prices (same as backtesting).
Stores baselines in database so they're consistent with backtesting.
Falls back to synthetic if real data unavailable (cached permanently).
"""

import json
import requests
import random
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import sys

sys.path.insert(0, str(Path(__file__).parent))
from database import db


DJIA_SYMBOLS = [
    "AAPL", "MSFT", "JPM", "V", "JNJ",
    "WMT", "PG", "UNH", "NVDA", "HD",
    "KO", "IBM", "MCD", "CAT", "AXP",
    "GS", "BA", "MMM", "AMGN", "INTC",
    "VZ", "PFE", "MRK", "HON", "CSCO",
    "NFLX", "TSLA", "CRM", "TRV", "DIS"
]


class BaselineDataFetcher:
    """Fetch and compute baseline equity curves from historical data."""
    
    def __init__(self, api_key: Optional[str] = None, 
                 secret_key: Optional[str] = None):
        """Initialize with Alpaca credentials."""
        if api_key is None:
            self._load_credentials()
        else:
            self.api_key = api_key
            self.secret_key = secret_key
        
        self.data_api_url = "https://data.alpaca.markets"
        self.headers = {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key,
        }
    
    def _load_credentials(self):
        """Load credentials from file."""
        creds_path = Path(__file__).parent.parent / "credentials" / "alpaca.json"
        if creds_path.exists():
            with open(creds_path, 'r') as f:
                creds = json.load(f)
                self.api_key = creds.get('api_key') or creds.get('apiKey')
                self.secret_key = creds.get('secret_key') or creds.get('secretKey')
    
    def fetch_djia_historical(self, days: int = 31) -> Optional[List[Dict]]:
        """
        Fetch DJIA historical data and create equity curve.
        Uses SPY (S&P 500 ETF) as proxy for market index.
        """
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            url = f"{self.data_api_url}/v2/stocks/SPY/bars"
            params = {
                "start": start_date.strftime("%Y-%m-%d"),  # Format: YYYY-MM-DD
                "end": end_date.strftime("%Y-%m-%d"),      # Format: YYYY-MM-DD
                "timeframe": "1D"
            }
            
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            
            if response.status_code != 200:
                print(f"Error fetching SPY: {response.status_code}")
                if response.status_code == 400:
                    print(f"  Details: {response.text[:200]}")
                return None
            
            bars = response.json().get("bars", [])
            if not bars:
                return None
            
            # Create equity curve from price bars
            initial_price = bars[0]["c"]
            equity_curve = []
            
            for bar in bars:
                price = bar["c"]
                equity = 100000 * (price / initial_price)
                equity_curve.append({
                    "timestamp": bar["t"],
                    "equity": round(equity, 2),
                    "cash": round(equity * 0.3, 2),
                    "positions_value": round(equity * 0.7, 2),
                    "daily_return": (price / initial_price) - 1
                })
            
            return equity_curve
        
        except Exception as e:
            print(f"Error in fetch_djia_historical: {e}")
            return None
    
    def fetch_buy_and_hold_djia(self, days: int = 31) -> Optional[List[Dict]]:
        """
        Fetch historical data for DJIA stocks and compute equal-weighted returns.
        """
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            # Sample first 10 DJIA stocks (faster than all 30)
            sample_symbols = DJIA_SYMBOLS[:10]
            
            all_bars = {}
            
            # Fetch bars for each symbol
            for symbol in sample_symbols:
                try:
                    url = f"{self.data_api_url}/v2/stocks/{symbol}/bars"
                    params = {
                        "start": start_date.strftime("%Y-%m-%d"),
                        "end": end_date.strftime("%Y-%m-%d"),
                        "timeframe": "1D"
                    }
                    
                    response = requests.get(url, headers=self.headers, params=params, timeout=5)
                    
                    if response.status_code == 200:
                        bars = response.json().get("bars", [])
                        if bars:
                            all_bars[symbol] = bars
                except Exception as e:
                    print(f"Error fetching {symbol}: {e}")
                    continue
            
            if not all_bars:
                return None
            
            # Build equal-weighted portfolio equity curve
            first_symbol = next(iter(all_bars.keys()))
            timestamps = [bar["t"] for bar in all_bars[first_symbol]]
            
            equity_curve = []
            
            for bar_idx, timestamp in enumerate(timestamps):
                total_return = 0
                count = 0
                
                for symbol in all_bars:
                    bars = all_bars[symbol]
                    if bar_idx < len(bars):
                        price = bars[bar_idx]["c"]
                        initial_price = bars[0]["c"]
                        daily_return = (price / initial_price) - 1
                        
                        total_return += daily_return
                        count += 1
                
                avg_return = total_return / count if count > 0 else 0
                equity = 100000 * (1 + avg_return)
                
                equity_curve.append({
                    "timestamp": timestamp,
                    "equity": round(equity, 2),
                    "cash": round(equity * 0.3, 2),
                    "positions_value": round(equity * 0.7, 2),
                    "daily_return": avg_return
                })
            
            return equity_curve
        
        except Exception as e:
            print(f"Error in fetch_buy_and_hold_djia: {e}")
            return None
    
    def create_baseline_runs(self, days: int = 31) -> bool:
        """
        Fetch real historical data and create baseline runs in database.
        Returns True if successful.
        """
        print(f"Fetching baseline data for {days} days...")
        
        # Fetch DJIA baseline
        print("  Fetching DJIA (SPY proxy)...")
        djia_curve = self.fetch_djia_historical(days=days)
        
        if not djia_curve:
            print("  ❌ Failed to fetch DJIA data")
            return False
        
        print(f"  ✅ DJIA: {len(djia_curve)} data points")
        
        # Fetch Buy-and-Hold baseline
        print("  Fetching Buy-and-Hold DJIA...")
        bah_curve = self.fetch_buy_and_hold_djia(days=days)
        
        if not bah_curve:
            print("  ❌ Failed to fetch Buy-and-Hold data")
            return False
        
        print(f"  ✅ Buy-and-Hold: {len(bah_curve)} data points")
        
        # Store in database
        now = datetime.now()
        
        # Store DJIA run
        djia_run_id = f"djia_baseline_{now.strftime('%Y%m%d_%H%M%S')}"
        djia_initial = djia_curve[0]["equity"]
        djia_final = djia_curve[-1]["equity"]
        djia_return = (djia_final - djia_initial) / djia_initial
        
        db.insert_run(
            run_id=djia_run_id,
            session_id="baseline-demo",
            agent_name="DJIA Index",
            mode="baseline",
            start_date=now.isoformat(),
            end_date=now.isoformat(),
            initial_equity=djia_initial,
            final_equity=djia_final,
            total_return=djia_return,
            sharpe_ratio=0.0,
            max_drawdown=0.0,
            num_trades=0
        )
        db.insert_equity_points(djia_run_id, djia_curve)
        print(f"  ✅ Stored DJIA run: {djia_run_id}")
        
        # Store Buy-and-Hold run
        bah_run_id = f"buy_and_hold_baseline_{now.strftime('%Y%m%d_%H%M%S')}"
        bah_initial = bah_curve[0]["equity"]
        bah_final = bah_curve[-1]["equity"]
        bah_return = (bah_final - bah_initial) / bah_initial
        
        db.insert_run(
            run_id=bah_run_id,
            session_id="baseline-demo",
            agent_name="Buy & Hold DJIA",
            mode="baseline",
            start_date=now.isoformat(),
            end_date=now.isoformat(),
            initial_equity=bah_initial,
            final_equity=bah_final,
            total_return=bah_return,
            sharpe_ratio=0.0,
            max_drawdown=0.0,
            num_trades=0
        )
        db.insert_equity_points(bah_run_id, bah_curve)
        print(f"  ✅ Stored Buy-and-Hold run: {bah_run_id}")
        
        return True


def create_synthetic_baselines(days: int = 31) -> bool:
    """
    Create synthetic baseline runs (cached forever after first creation).
    Used when Alpaca data API is not available.
    """
    import random
    
    now = datetime.now()
    
    # Create DJIA synthetic baseline
    djia_run_id = f"djia_baseline_synthetic_{now.strftime('%Y%m%d')}"
    djia_curve = []
    djia_equity = 100000
    
    start_date = now - timedelta(days=days)
    current_date = start_date
    
    while current_date <= now:
        if current_date.weekday() < 5:  # Skip weekends
            drift = 0.0004
            volatility = 0.012
            daily_return = drift + volatility * random.gauss(0, 1)
            djia_equity *= (1 + daily_return)
            
            djia_curve.append({
                "timestamp": current_date.isoformat(),
                "equity": round(djia_equity, 2),
                "daily_return": daily_return
            })
        
        current_date += timedelta(days=1)
    
    # Create Buy-and-Hold synthetic baseline
    bah_run_id = f"buy_and_hold_baseline_synthetic_{now.strftime('%Y%m%d')}"
    bah_curve = []
    bah_equity = 100000
    
    current_date = start_date
    
    while current_date <= now:
        if current_date.weekday() < 5:  # Skip weekends
            drift = 0.0003
            volatility = 0.015
            daily_return = drift + volatility * random.gauss(0, 1)
            bah_equity *= (1 + daily_return)
            
            bah_curve.append({
                "timestamp": current_date.isoformat(),
                "equity": round(bah_equity, 2),
                "daily_return": daily_return
            })
        
        current_date += timedelta(days=1)
    
    # Store in database
    try:
        djia_initial = djia_curve[0]["equity"]
        djia_final = djia_curve[-1]["equity"]
        djia_return = (djia_final - djia_initial) / djia_initial
        
        db.insert_run(
            run_id=djia_run_id,
            session_id="baseline-demo",
            agent_name="DJIA Index (Synthetic)",
            mode="baseline",
            start_date=now.isoformat(),
            end_date=now.isoformat(),
            initial_equity=djia_initial,
            final_equity=djia_final,
            total_return=djia_return,
            sharpe_ratio=0.0,
            max_drawdown=0.0,
            num_trades=0
        )
        # Add missing fields that database expects
        djia_curve_with_fields = []
        for point in djia_curve:
            djia_curve_with_fields.append({
                "timestamp": point["timestamp"],
                "equity": point["equity"],
                "cash": point["equity"] * 0.3,  # Assume 30% cash
                "positions_value": point["equity"] * 0.7,  # 70% in positions
                "daily_return": point["daily_return"]
            })
        
        db.insert_equity_points(djia_run_id, djia_curve_with_fields)
        
        bah_initial = bah_curve[0]["equity"]
        bah_final = bah_curve[-1]["equity"]
        bah_return = (bah_final - bah_initial) / bah_initial
        
        db.insert_run(
            run_id=bah_run_id,
            session_id="baseline-demo",
            agent_name="Buy & Hold DJIA (Synthetic)",
            mode="baseline",
            start_date=now.isoformat(),
            end_date=now.isoformat(),
            initial_equity=bah_initial,
            final_equity=bah_final,
            total_return=bah_return,
            sharpe_ratio=0.0,
            max_drawdown=0.0,
            num_trades=0
        )
        
        # Add missing fields that database expects
        bah_curve_with_fields = []
        for point in bah_curve:
            bah_curve_with_fields.append({
                "timestamp": point["timestamp"],
                "equity": point["equity"],
                "cash": point["equity"] * 0.3,
                "positions_value": point["equity"] * 0.7,
                "daily_return": point["daily_return"]
            })
        
        db.insert_equity_points(bah_run_id, bah_curve_with_fields)
        
        print(f"✅ Created synthetic baselines (cached forever)")
        return True
    except Exception as e:
        print(f"❌ Error storing synthetic baselines: {e}")
        return False


def create_baselines_if_not_exists(days: int = 31):
    """
    Create baseline runs if they don't already exist in database.
    Called once on startup, then skipped on subsequent startups.
    
    Try real data first, fallback to synthetic (cached).
    """
    try:
        # Check if baseline runs already exist
        runs = db.get_runs_by_mode("baseline")
        
        if runs and len(runs) >= 2:
            # Baselines already exist, don't re-fetch
            djia_runs = [r for r in runs if "djia" in r.get("agent_name", "").lower()]
            bah_runs = [r for r in runs if "buy" in r.get("agent_name", "").lower()]
            
            print(f"✅ Baselines already cached ({len(djia_runs)} DJIA + {len(bah_runs)} B&H)")
            return True
        
        print("📊 Creating baselines (one-time setup)...")
        
        # Try to fetch real data
        print("  Attempting real data from Alpaca...")
        fetcher = BaselineDataFetcher()
        success = fetcher.create_baseline_runs(days=days)
        
        if success:
            print("✅ Real baselines created and cached")
            return True
        else:
            # Fallback to synthetic (same quality for comparison, just not "real")
            print("  Alpaca data unavailable, using synthetic (will be cached)")
            success = create_synthetic_baselines(days=days)
            if success:
                print("✅ Synthetic baselines created and cached")
            return success
    
    except Exception as e:
        print(f"⚠️ Error creating baselines: {e}")
        return False


if __name__ == "__main__":
    create_baselines_if_not_exists(days=31)
