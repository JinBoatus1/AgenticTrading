"""
Simple in-memory cache with TTL (time-to-live) for paper trading data.
Reduces redundant API calls to Alpaca.
"""

import json
import time
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from threading import Lock


class CachedData:
    """Cached item with expiration."""
    
    def __init__(self, data: Any, ttl_seconds: int = 30):
        self.data = data
        self.created_at = time.time()
        self.ttl_seconds = ttl_seconds
    
    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        return time.time() - self.created_at > self.ttl_seconds
    
    def get(self) -> Optional[Any]:
        """Get data if not expired, None otherwise."""
        if self.is_expired():
            return None
        return self.data


class PaperTradingCache:
    """Cache for paper trading API responses."""
    
    def __init__(self):
        self.cache: Dict[str, CachedData] = {}
        self.lock = Lock()
    
    def get(self, key: str) -> Optional[Any]:
        """Get cached value if not expired."""
        with self.lock:
            if key in self.cache:
                data = self.cache[key].get()
                if data is not None:
                    return data
                else:
                    # Expired, remove from cache
                    del self.cache[key]
        return None
    
    def set(self, key: str, value: Any, ttl_seconds: int = 30):
        """Store value with TTL."""
        with self.lock:
            self.cache[key] = CachedData(value, ttl_seconds)
    
    def invalidate(self, key: str):
        """Remove cached entry."""
        with self.lock:
            if key in self.cache:
                del self.cache[key]
    
    def clear_all(self):
        """Clear all cache entries."""
        with self.lock:
            self.cache.clear()
    
    def stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        with self.lock:
            expired = sum(1 for item in self.cache.values() if item.is_expired())
            return {
                "total_items": len(self.cache),
                "expired_items": expired,
                "active_items": len(self.cache) - expired
            }


# Singleton instance
paper_trading_cache = PaperTradingCache()


# Cache key constants
CACHE_KEY_ACCOUNT = "paper:account"
CACHE_KEY_POSITIONS = "paper:positions"
CACHE_KEY_TRADES = "paper:trades"
CACHE_KEY_PORTFOLIO_HISTORY = "paper:portfolio_history"
CACHE_KEY_BASELINES = "paper:baselines"

# TTL settings (in seconds)
TTL_ACCOUNT = 30          # Account updates less frequently
TTL_POSITIONS = 30        # Positions update on trades
TTL_TRADES = 60           # Trade history changes infrequently
TTL_PORTFOLIO_HISTORY = 120  # Portfolio history very stable
TTL_BASELINES = 3600      # Baselines update daily (1 hour cache)
