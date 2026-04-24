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
            Dict with keys: symbol, price, change, changePercent, timestamp
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
                    price = quote.get("ap") or quote.get("bp") or quote.get("p", 0)  # ask, bid, or last price
                    
                    # Try to get previous close for comparison
                    prev_close = self._get_previous_close(symbol)
                    
                    if prev_close and prev_close > 0:
                        change = price - prev_close
                        change_percent = (change / prev_close) * 100
                    else:
                        change = 0
                        change_percent = 0
                    
                    return {
                        "symbol": symbol,
                        "price": round(price, 2),
                        "change": round(change, 2),
                        "changePercent": round(change_percent, 2),
                        "timestamp": datetime.now().isoformat()
                    }
            else:
                print(f"Error fetching {symbol}: {response.status_code} - {response.text[:200]}")
                return None
        
        except Exception as e:
            print(f"Exception fetching {symbol}: {e}")
            return None
    
    def _get_previous_close(self, symbol: str) -> Optional[float]:
        """Get previous close price for % change calculation."""
        try:
            url = f"{self.base_url}/v1/assets/{symbol}"
            response = requests.get(url, headers=self.headers, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                return data.get("prevclose")
        except Exception as e:
            print(f"Error getting previous close for {symbol}: {e}")
        
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
