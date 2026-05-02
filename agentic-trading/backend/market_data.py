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
                    quote_timestamp = quote.get("t", "unknown")
                    
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
                        price_source = None
                        
                        if ap is not None and ap > 0 and bp is not None and bp > 0:
                            current_price = (ap + bp) / 2
                            price_source = "midpoint(ap,bp)"
                        elif ap is not None and ap > 0:
                            current_price = ap
                            price_source = "ask(ap)"
                        elif bp is not None and bp > 0:
                            current_price = bp
                            price_source = "bid(bp)"
                        elif p is not None and p > 0:
                            current_price = p
                            price_source = "last_trade(p)"
                        
                        if current_price is None or current_price <= 0:
                            print(f"❌ {symbol}: Could not determine current price (ap={ap}, bp={bp}, p={p})")
                            return None
                        
                        print(f"✅ {symbol}: current_price={current_price} source={price_source} ts={quote_timestamp}")
                    except Exception as e:
                        print(f"❌ {symbol}: Error calculating current price: {e}")
                        return None
                    
                    # STEP 2: Get previous close from historical daily bars
                    prev_close = self._get_previous_close(symbol)
                    
                    # STEP 3: Calculate % change
                    if prev_close and prev_close > 0:
                        change_percent = ((current_price - prev_close) / prev_close) * 100
                        print(f"✅ {symbol}: change_percent={change_percent:.2f}% (current={current_price} - prev_close={prev_close})")
                    else:
                        # If we can't get previous close, return None for change_percent
                        change_percent = None
                        print(f"⚠️ {symbol}: No previous_close available, showing '--' for % change")
                    
                    return {
                        "symbol": symbol,
                        "price": round(current_price, 2),
                        "changePercent": round(change_percent, 2) if change_percent is not None else None,
                        "timestamp": datetime.now().isoformat()
                    }
            else:
                print(f"❌ {symbol}: Error fetching quote: {response.status_code} - {response.text[:200]}")
                return None
        
        except Exception as e:
            print(f"❌ {symbol}: Exception fetching quote: {e}")
            return None
    
    def _get_previous_close(self, symbol: str) -> Optional[float]:
        """
        Get previous day's close price from historical daily bars.
        
        Returns the close price (field 'c') from the most recent completed trading day.
        
        Strategy:
        1. Try IEX feed (free tier has access)
        2. If IEX fails, try SIP with delayed end time (15+ mins ago)
        3. If both fail, return None
        """
        try:
            from datetime import datetime, timedelta
            
            # Fetch last 5 trading days to ensure we get the most recent completed day
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            
            # ===== ATTEMPT 1: Try IEX feed (free tier) =====
            url_iex = f"{self.data_api_url}/v2/stocks/{symbol}/bars?timeframe=1Day&start={start_date}&end={end_date}&limit=5&feed=iex"
            print(f"  Fetching {symbol} previous_close from IEX: {url_iex}")
            
            response = requests.get(url_iex, headers=self.headers, timeout=5)
            print(f"  IEX response: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                if "bars" in data and len(data["bars"]) > 0:
                    bars = data["bars"]
                    
                    # Sort by timestamp descending (most recent first)
                    bars_sorted = sorted(bars, key=lambda x: x.get("t", ""), reverse=True)
                    
                    if len(bars_sorted) > 1:
                        # Use 2nd most recent (in case most recent is incomplete)
                        try:
                            bar_timestamp = bars_sorted[1].get("t", "unknown")
                            prev_close = float(bars_sorted[1].get("c", 0))
                            print(f"✅ {symbol}: previous_close={prev_close} (from IEX feed, ts={bar_timestamp})")
                            return prev_close if prev_close > 0 else None
                        except (ValueError, TypeError) as e:
                            print(f"⚠️ {symbol}: Could not parse IEX bar data: {e}")
                            pass
                    elif len(bars_sorted) == 1:
                        try:
                            bar_timestamp = bars_sorted[0].get("t", "unknown")
                            prev_close = float(bars_sorted[0].get("c", 0))
                            print(f"✅ {symbol}: previous_close={prev_close} (from IEX feed - 1 bar only, ts={bar_timestamp})")
                            return prev_close if prev_close > 0 else None
                        except (ValueError, TypeError) as e:
                            print(f"⚠️ {symbol}: Could not parse IEX bar data: {e}")
                            pass
            
            # ===== ATTEMPT 2: Try SIP with delayed end time (15+ mins ago) =====
            # Only query SIP data up to 15 minutes ago to avoid "recent SIP data" restriction
            delayed_end = datetime.now() - timedelta(minutes=15)
            delayed_end_str = delayed_end.strftime("%Y-%m-%d")
            
            url_sip = f"{self.data_api_url}/v2/stocks/{symbol}/bars?timeframe=1Day&start={start_date}&end={delayed_end_str}&limit=5"
            print(f"  Fetching {symbol} previous_close from delayed SIP (end={delayed_end_str}): {url_sip}")
            
            response = requests.get(url_sip, headers=self.headers, timeout=5)
            print(f"  SIP response: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                if "bars" in data and len(data["bars"]) > 0:
                    bars = data["bars"]
                    
                    # Sort by timestamp descending (most recent first)
                    bars_sorted = sorted(bars, key=lambda x: x.get("t", ""), reverse=True)
                    
                    if len(bars_sorted) > 1:
                        try:
                            bar_timestamp = bars_sorted[1].get("t", "unknown")
                            prev_close = float(bars_sorted[1].get("c", 0))
                            print(f"✅ {symbol}: previous_close={prev_close} (from delayed SIP, ts={bar_timestamp})")
                            return prev_close if prev_close > 0 else None
                        except (ValueError, TypeError) as e:
                            print(f"⚠️ {symbol}: Could not parse SIP bar data: {e}")
                            pass
                    elif len(bars_sorted) == 1:
                        try:
                            bar_timestamp = bars_sorted[0].get("t", "unknown")
                            prev_close = float(bars_sorted[0].get("c", 0))
                            print(f"✅ {symbol}: previous_close={prev_close} (from delayed SIP - 1 bar only, ts={bar_timestamp})")
                            return prev_close if prev_close > 0 else None
                        except (ValueError, TypeError) as e:
                            print(f"⚠️ {symbol}: Could not parse SIP bar data: {e}")
                            pass
            
            # ===== BOTH FAILED: Return None =====
            print(f"⚠️ {symbol}: Could not fetch previous_close (IEX and SIP both unavailable)")
            return None
                    
        except Exception as e:
            print(f"⚠️ Error getting previous close for {symbol}: {e}")
        
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
