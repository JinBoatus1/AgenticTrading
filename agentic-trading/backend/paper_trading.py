"""
Paper Trading Module - Connect to Alpaca paper trading account.
Fetches live account data, positions, and trade history.
"""

import json
import requests
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass


@dataclass
class Position:
    """Represents a current position."""
    symbol: str
    qty: float
    avg_fill_price: float
    current_price: float
    unrealized_pl: float
    unrealized_plpc: float
    side: str  # 'long' or 'short'
    market_value: float


@dataclass
class Trade:
    """Represents a single trade."""
    id: str
    symbol: str
    qty: float
    side: str
    filled_avg_price: float
    filled_at: str
    order_status: str


class AlpacaPaperTradingClient:
    """Interface to Alpaca paper trading API."""
    
    def __init__(self, api_key: Optional[str] = None, 
                 secret_key: Optional[str] = None):
        """Initialize with Alpaca credentials."""
        if api_key is None:
            self._load_from_credentials()
        else:
            self.api_key = api_key
            self.secret_key = secret_key
        
        self.base_url = "https://paper-api.alpaca.markets"
        self.headers = {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key,
        }
    
    def _load_from_credentials(self):
        """Load credentials from credentials/alpaca.json"""
        creds_path = Path(__file__).parent.parent / "credentials" / "alpaca.json"
        
        if creds_path.exists():
            with open(creds_path, 'r') as f:
                creds = json.load(f)
                self.api_key = creds.get('api_key') or creds.get('apiKey')
                self.secret_key = creds.get('secret_key') or creds.get('secretKey')
        else:
            raise FileNotFoundError(f"Credentials file not found: {creds_path}")
    
    def get_account(self) -> Optional[Dict]:
        """
        Get current account info.
        
        Returns:
            Dict with: cash, equity, buying_power, portfolio_value, etc.
        """
        try:
            url = f"{self.base_url}/v2/account"
            response = requests.get(url, headers=self.headers, timeout=10)
            
            if response.status_code == 200:
                account = response.json()
                return {
                    "cash": float(account.get("cash", 0)),
                    "equity": float(account.get("equity", 0)),
                    "buying_power": float(account.get("buying_power", 0)),
                    "portfolio_value": float(account.get("portfolio_value", 0)),
                    "multiplier": int(account.get("multiplier", 1)),
                    "account_number": account.get("account_number"),
                    "account_status": account.get("status"),
                    "created_at": account.get("created_at"),
                }
            else:
                print(f"Error fetching account: {response.status_code}")
                return None
        except Exception as e:
            print(f"Exception in get_account: {e}")
            return None
    
    def get_positions(self) -> List[Position]:
        """
        Get all current positions.
        
        Returns:
            List of Position objects
        """
        try:
            url = f"{self.base_url}/v2/positions"
            response = requests.get(url, headers=self.headers, timeout=10)
            
            if response.status_code == 200:
                positions_data = response.json()
                positions = []
                
                for pos in positions_data:
                    position = Position(
                        symbol=pos.get("symbol"),
                        qty=float(pos.get("qty", 0)),
                        avg_fill_price=float(pos.get("avg_fill_price", 0)),
                        current_price=float(pos.get("current_price", 0)),
                        unrealized_pl=float(pos.get("unrealized_pl", 0)),
                        unrealized_plpc=float(pos.get("unrealized_plpc", 0)),
                        side=pos.get("side"),
                        market_value=float(pos.get("market_value", 0))
                    )
                    positions.append(position)
                
                return positions
            else:
                print(f"Error fetching positions: {response.status_code}")
                return []
        except Exception as e:
            print(f"Exception in get_positions: {e}")
            return []
    
    def get_orders(self, limit: int = 50, status: str = "all") -> List[Dict]:
        """
        Get order history.
        
        Args:
            limit: Max orders to return
            status: 'all', 'open', 'closed', 'cancelled'
        
        Returns:
            List of order dicts
        """
        try:
            url = f"{self.base_url}/v2/orders"
            params = {"limit": limit, "status": status}
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Error fetching orders: {response.status_code}")
                return []
        except Exception as e:
            print(f"Exception in get_orders: {e}")
            return []
    
    def get_activities(self, activity_type: str = "FILL", limit: int = 100) -> List[Dict]:
        """
        Get trade activity (fills).
        
        Args:
            activity_type: 'FILL' for trades
            limit: Max activities to return
        
        Returns:
            List of activity dicts
        """
        try:
            url = f"{self.base_url}/v2/account/activities"
            params = {"activity_type": activity_type, "limit": limit}
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Error fetching activities: {response.status_code}")
                return []
        except Exception as e:
            print(f"Exception in get_activities: {e}")
            return []
    
    def get_portfolio_history(self, timeframe: str = "1D") -> Optional[Dict]:
        """
        Get portfolio performance history.
        
        Args:
            timeframe: '1D', '1W', '1M', '3M', '1A' (all)
        
        Returns:
            Dict with equity curve data
        """
        try:
            url = f"{self.base_url}/v2/account/portfolio/history"
            params = {"timeframe": timeframe}
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Error fetching portfolio history: {response.status_code}")
                return None
        except Exception as e:
            print(f"Exception in get_portfolio_history: {e}")
            return None


class PaperTradingSession:
    """Track a paper trading session with equity history."""
    
    def __init__(self, run_id: str, agent_name: str):
        self.run_id = run_id
        self.agent_name = agent_name
        self.start_time = datetime.now()
        self.equity_history = []
        self.trades_log = []
        self.last_equity = None
        self.initial_equity = None
    
    def add_equity_snapshot(self, equity: float, cash: float, 
                          positions_value: float, daily_return: Optional[float] = None):
        """Record an equity snapshot."""
        timestamp = datetime.now().isoformat()
        
        snapshot = {
            "timestamp": timestamp,
            "equity": equity,
            "cash": cash,
            "positions_value": positions_value,
            "daily_return": daily_return
        }
        
        self.equity_history.append(snapshot)
        self.last_equity = equity
        
        if self.initial_equity is None:
            self.initial_equity = equity
    
    def add_trade(self, symbol: str, qty: float, side: str, 
                  price: float, reason: str = ""):
        """Log a trade."""
        timestamp = datetime.now().isoformat()
        
        trade = {
            "timestamp": timestamp,
            "symbol": symbol,
            "qty": qty,
            "side": side,
            "price": price,
            "value": qty * price,
            "reason": reason
        }
        
        self.trades_log.append(trade)
    
    def get_metrics(self) -> Dict:
        """Calculate session metrics."""
        if not self.equity_history or self.initial_equity is None:
            return {}
        
        final_equity = self.last_equity or self.initial_equity
        total_return = ((final_equity - self.initial_equity) / self.initial_equity) * 100
        
        # Calculate simple stats
        equities = [s["equity"] for s in self.equity_history]
        max_equity = max(equities) if equities else self.initial_equity
        min_equity = min(equities) if equities else self.initial_equity
        max_drawdown = ((min_equity - max_equity) / max_equity) * 100 if max_equity > 0 else 0
        
        return {
            "total_return": round(total_return, 2),
            "max_drawdown": round(max_drawdown, 2),
            "final_equity": round(final_equity, 2),
            "num_trades": len(self.trades_log)
        }


def create_paper_trading_session(agent_name: str) -> str:
    """
    Create a new paper trading session and return run_id.
    
    Returns:
        run_id: Unique identifier for this session
    """
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id = f"{agent_name}_{timestamp}"
    return run_id
