"""
Market data fetcher - connects to Alpaca API for live quotes.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional
import requests
from datetime import datetime

class AlpacaMarketData:
    """Fetch live market quotes from Alpaca API."""
    
    def __init__(self, api_key: Optional[str] = None, secret_key: Optional[str] = None, 
                 paper: bool = True):
        """
        Initialize with Alpaca credentials.
        
        Args:
            api_key: Alpaca API key
            secret_key: Alpaca secret key
            paper: Use paper trading endpoint (default True)
        """
        # Always initialize these first
        self.api_key = None
        self.secret_key = None
        
        # Try to load from credentials
        if api_key is None:
            self._load_from_credentials()
        else:
            self.api_key = api_key
            self.secret_key = secret_key
        
        self.paper = paper
        self.base_url = "https://paper-api.alpaca.markets" if paper else "https://api.alpaca.markets"
        self.data_api_url = "https://data.alpaca.markets"
        
        self.headers = {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key,
        }
    
    def _load_from_credentials(self):
        """Load credentials from environment variables or credentials file"""
        # Try environment variables first (for Render, Docker, etc.)
        self.api_key = os.getenv('ALPACA_API_KEY')
        self.secret_key = os.getenv('ALPACA_SECRET_KEY')
        
        if self.api_key and self.secret_key:
            return
        
        # Fall back to credentials file (for local development)
        creds_path = Path(__file__).parent.parent / "credentials" / "alpaca.json"
        
        if creds_path.exists():
            with open(creds_path, 'r') as f:
                creds = json.load(f)
                self.api_key = creds.get('api_key') or creds.get('apiKey')
                self.secret_key = creds.get('secret_key') or creds.get('secretKey')
                self.paper = creds.get('paper', True)
        else:
            raise FileNotFoundError(f"Credentials file not found: {creds_path}")
    
    def get_quote(self, symbol: str) -> Optional[Dict]:
        """
        Get latest quote for a symbol from Alpaca Data API.
        
        Returns:
            Dict with keys: symbol, price, changePercent, timestamp
            changePercent is percentage change vs previous day's close
        """
        try:
            # Use Alpaca Data API endpoint
            url = f"{self.data_api_url}/v2/stocks/{symbol}/quotes/latest"
            
            response = requests.get(url, headers=self.headers, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                
                # Extract quote from response
                if "quote" in data:
                    quote = data["quote"]
                    
                    # STEP 1: Get current price using bid/ask midpoint
                    try:
                        # Extract and convert to float
                        ap = quote.get("ap")
                        bp = quote.get("bp")
                        p = quote.get("p")
                        
                        # Convert all to float, skip if conversion fails
                        try:
                            ap = float(ap) if ap else None
                        except (ValueError, TypeError):
                            ap = None
                        
                        try:
                            bp = float(bp) if bp else None
                        except (ValueError, TypeError):
                            bp = None
                        
                        try:
                            p = float(p) if p else None
                        except (ValueError, TypeError):
                            p = None
                        
                        # Calculate current price with fallback logic
                        current_price = None
                        if ap is not None and ap > 0 and bp is not None and bp > 0:
                            current_price = (ap + bp) / 2
                        elif ap is not None and ap > 0:
                            current_price = ap
                        elif bp is not None and bp > 0:
                            current_price = bp
                        elif p is not None and p > 0:
                            current_price = p
                        
                        if current_price is None or current_price <= 0:
                            print(f"DEBUG {symbol}: Could not determine current price (ap={ap}, bp={bp}, p={p})")
                            return None
                    except Exception as e:
                        print(f"Error calculating current price for {symbol}: {e}")
                        return None
                    
                    # STEP 2: Get previous close from historical daily bars
                    prev_close = self._get_previous_close(symbol)
                    
                    # STEP 3: Calculate % change
                    if prev_close and prev_close > 0:
                        change_percent = ((current_price - prev_close) / prev_close) * 100
                    else:
                        # If we can't get previous close, return None for change_percent
                        change_percent = None
                    
                    return {
                        "symbol": symbol,
                        "price": round(current_price, 2),
                        "changePercent": round(change_percent, 2) if change_percent is not None else None,
                        "timestamp": datetime.now().isoformat()
                    }
            else:
                print(f"Error fetching {symbol}: {response.status_code} - {response.text[:200]}")
                return None
        
        except Exception as e:
            print(f"Exception fetching {symbol}: {e}")
            return None
    
    def _get_previous_close(self, symbol: str) -> Optional[float]:
        """
        Get previous day's close price from historical daily bars.
        
        Returns the close price (field 'c') from the most recent completed trading day.
        """
        try:
            from datetime import datetime, timedelta
            
            # Fetch last 5 trading days to ensure we get the most recent completed day
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            
            # Alpaca bars endpoint with correct timeframe format
            url = f"{self.data_api_url}/v2/stocks/{symbol}/bars?timeframe=1Day&start={start_date}&end={end_date}&limit=5"
            
            response = requests.get(url, headers=self.headers, timeout=5)
            
            print(f"DEBUG {symbol}: Fetching bars from {url}")
            
            if response.status_code == 200:
                data = response.json()
                
                # Get all bars and sort by timestamp
                if "bars" in data and len(data["bars"]) > 0:
                    bars = data["bars"]
                    
                    # Sort by timestamp descending (most recent first)
                    bars_sorted = sorted(bars, key=lambda x: x.get("t", ""), reverse=True)
                    
                    # Get the most recent bar (could be today or yesterday depending on market hours)
                    # The 'c' field is the close price for that day
                    if len(bars_sorted) > 0:
                        most_recent_close = float(bars_sorted[0].get("c", 0))
                        
                        # If current time is after market close (4 PM ET), use today's bar
                        # Otherwise use yesterday's bar (second most recent)
                        if len(bars_sorted) > 1:
                            # Use the bar before the most recent one as "previous close"
                            # (assuming most recent might be today's incomplete bar)
                            try:
                                prev_close = float(bars_sorted[1].get("c", 0))
                                print(f"DEBUG {symbol}: previous_close={prev_close} (from 2nd most recent bar)")
                                return prev_close if prev_close > 0 else None
                            except (ValueError, TypeError) as e:
                                print(f"DEBUG {symbol}: Could not convert close price: {e}")
                                return None
                        else:
                            try:
                                print(f"DEBUG {symbol}: previous_close={most_recent_close} (only one bar available)")
                                return most_recent_close if most_recent_close > 0 else None
                            except (ValueError, TypeError) as e:
                                print(f"DEBUG {symbol}: Could not convert close price: {e}")
                                return None
            else:
                error_msg = response.text[:300] if response.text else "No response"
                print(f"Warning: Could not fetch bars for {symbol}: {response.status_code}")
                if "subscription does not permit" in response.text.lower():
                    print(f"  (Subscription limitation - historical bar data not available)")
                print(f"  Response: {error_msg}")
                # Return None - will display "--" in UI
                return None
                    
        except Exception as e:
            print(f"Warning: Error getting previous close for {symbol}: {e}")
            # Return None - will display "--" in UI
        
        return None
    
    def get_quotes_batch(self, symbols: List[str]) -> List[Dict]:
        """
        Get quotes for multiple symbols.
        
        Args:
            symbols: List of ticker symbols
        
        Returns:
            List of quote dicts
        """
        quotes = []
        for symbol in symbols:
            quote = self.get_quote(symbol)
            if quote:
                quotes.append(quote)
        
        return quotes
    
    def get_crypto_quote(self, symbol: str) -> Optional[Dict]:
        """
        Get crypto quote (BTC, ETH, etc.) using external API.
        Falls back to CoinGecko free API.
        """
        try:
            # Map ticker to CoinGecko ID
            crypto_map = {
                "BTC": "bitcoin",
                "ETH": "ethereum",
                "XRP": "ripple",
                "SOL": "solana",
            }
            
            coin_id = crypto_map.get(symbol)
            if not coin_id:
                return None
            
            url = "https://api.coingecko.com/api/v3/simple/price"
            params = {
                "ids": coin_id,
                "vs_currencies": "usd",
                "include_24hr_change": "true"
            }
            
            response = requests.get(url, params=params, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                price_data = data.get(coin_id, {})
                price = price_data.get("usd", 0)
                change_percent = price_data.get("usd_24h_change", 0)
                
                # Format price (show thousands as k)
                if price >= 1000:
                    formatted_price = f"{price/1000:.1f}k"
                else:
                    formatted_price = f"{price:.2f}"
                
                return {
                    "symbol": symbol,
                    "price": formatted_price,
                    "change": None,  # We only have percent
                    "changePercent": round(change_percent, 2),
                    "timestamp": datetime.now().isoformat()
                }
        except Exception as e:
            print(f"Error fetching crypto {symbol}: {e}")
        
        return None


def get_market_quotes(symbols: List[str]) -> List[Dict]:
    """
    Convenience function to fetch quotes for stocks and crypto.
    
    Usage:
        quotes = get_market_quotes(["AAPL", "NVDA", "MSFT", "BTC"])
    """
    # Separate stocks and crypto
    stocks = [s for s in symbols if s not in ["BTC", "ETH", "XRP", "SOL"]]
    crypto = [s for s in symbols if s in ["BTC", "ETH", "XRP", "SOL"]]
    
    quotes = []
    
    # Fetch stocks
    if stocks:
        try:
            market_data = AlpacaMarketData()
            quotes.extend(market_data.get_quotes_batch(stocks))
        except Exception as e:
            print(f"Error initializing Alpaca: {e}")
    
    # Fetch crypto
    if crypto:
        try:
            market_data = AlpacaMarketData()
            for symbol in crypto:
                quote = market_data.get_crypto_quote(symbol)
                if quote:
                    quotes.append(quote)
        except Exception as e:
            print(f"Error fetching crypto: {e}")
    
    return quotes
