"""
FastAPI backend for agentic trading dashboard.
Serves equity curves, run metadata, and comparison data.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
from database import db
from market_data import get_market_quotes
from paper_trading import AlpacaPaperTradingClient, create_paper_trading_session
from paper_baselines import create_paper_baselines_if_not_exists
from baselines_endpoint import get_baselines_from_db
from cache import paper_trading_cache, CACHE_KEY_ACCOUNT, CACHE_KEY_POSITIONS, CACHE_KEY_TRADES, CACHE_KEY_PORTFOLIO_HISTORY, CACHE_KEY_BASELINES, TTL_ACCOUNT, TTL_POSITIONS, TTL_TRADES, TTL_PORTFOLIO_HISTORY, TTL_BASELINES
import pytz

# ============================================================================
# Helper: Filter to Market Hours Only
# ============================================================================

def filter_market_hours(equity_points: List[dict]) -> List[dict]:
    """
    Filter equity data to only include market hours.
    Requirements:
    - Weekday (Monday-Friday): 0=Mon, 6=Sun
    - Time: 9:30 AM - 4:00 PM ET
    - Removes weekends, pre-market, after-hours, and overnight data
    """
    if not equity_points:
        return []
    
    et_tz = pytz.timezone('US/Eastern')
    filtered = []
    removed_count = 0
    
    for point in equity_points:
        try:
            # Parse timestamp
            ts = datetime.fromisoformat(point['timestamp'].replace('Z', '+00:00'))
            ts_et = ts.astimezone(et_tz)
            
            # Check weekday (0=Mon, 4=Fri, 5=Sat, 6=Sun)
            weekday = ts_et.weekday()
            is_weekday = weekday < 5  # Monday-Friday only
            
            # Check time: 9:30 AM through 4:00 PM ET
            hour = ts_et.hour
            minute = ts_et.minute
            is_market_hours = ((hour == 9 and minute >= 30) or (hour > 9 and hour < 16) or (hour == 16 and minute == 0))
            
            if is_weekday and is_market_hours:
                filtered.append(point)
            else:
                removed_count += 1
        except Exception as e:
            print(f"Warning: Could not parse timestamp {point.get('timestamp')}: {e}")
            removed_count += 1
            continue
    
    if removed_count > 0:
        print(f"✅ filter_market_hours: {len(equity_points)} → {len(filtered)} points (removed {removed_count} non-market-hours)")
    
    if len(filtered) == 0 and len(equity_points) > 0:
        print(f"⚠️ WARNING: filter_market_hours removed ALL {len(equity_points)} points! Check timezone or data format.")
    
    return filtered

# Initialize FastAPI app
app = FastAPI(
    title="Agentic Trading Dashboard API",
    description="Backend API for backtesting and paper trading equity curves",
    version="1.0.0"
)

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# CSP Middleware: Permit Chart.js and inline scripts (for development)
from starlette.middleware.base import BaseHTTPMiddleware

class CSPHeaderMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        # Allow Chart.js and scripts from same origin, plus unsafe-inline for development
        response.headers["Content-Security-Policy"] = "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline'; connect-src *; img-src * data:;"
        # Explicitly set CORS headers
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response

app.add_middleware(CSPHeaderMiddleware)

# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize API server."""
    print("🚀 Starting API server...")
    print("📊 Backtesting: Baselines created by scripts/backtest_hourly_agent.py")
    print("📊 Paper Trading: Baselines initialized on startup...")
    
    # Initialize paper trading baselines (non-blocking)
    import threading
    
    def init_paper_baselines():
        """Background initialization - create paper trading baselines only."""
        try:
            create_paper_baselines_if_not_exists()
        except Exception as e:
            print(f"⚠️ Paper baseline initialization error: {e}")
    
    thread = threading.Thread(target=init_paper_baselines, daemon=True)
    thread.start()
    # Don't wait - server starts immediately


# ============================================================================
# Pydantic Models (Response structures)
# ============================================================================

class EquityPoint(BaseModel):
    timestamp: str
    equity: float
    cash: float
    positions_value: float
    daily_return: Optional[float] = None


class RunMetadata(BaseModel):
    run_id: str
    agent_name: str
    mode: str
    start_date: str
    end_date: str
    initial_equity: float
    final_equity: Optional[float] = None
    total_return: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    max_drawdown: Optional[float] = None
    num_trades: int = 0
    created_at: str


class EquityCurve(BaseModel):
    run_id: str
    agent_name: str
    data: List[EquityPoint]
    metrics: dict


class ComparisonResponse(BaseModel):
    runs: List[EquityCurve]
    summary: dict


# ============================================================================
# API Routes
# ============================================================================

@app.get("/health")
async def health():
    """Health check."""
    return {"status": "ok"}


# ============================================================================
# Backtest Routes
# ============================================================================

@app.get("/api/backtest/runs", response_model=List[RunMetadata])
async def get_backtest_runs():
    """Get all backtest runs."""
    runs = db.get_runs_by_mode("backtest")
    return [RunMetadata(**run) for run in runs]


@app.get("/api/backtest/{run_id}", response_model=EquityCurve)
async def get_backtest_run(run_id: str):
    """Get specific backtest run with equity curve."""
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    equity_data = db.get_equity_curve(run_id)
    
    return EquityCurve(
        run_id=run_id,
        agent_name=run['agent_name'],
        data=[EquityPoint(**point) for point in equity_data],
        metrics={
            'total_return': run['total_return'],
            'sharpe_ratio': run['sharpe_ratio'],
            'max_drawdown': run['max_drawdown'],
            'num_trades': run['num_trades']
        }
    )


@app.get("/api/backtest/compare/latest", response_model=ComparisonResponse)
async def compare_latest_backtests():
    """Compare the latest backtest runs + baselines."""
    # Get both backtest and baseline runs
    backtest_runs = db.get_runs_by_mode("backtest") or []
    baseline_runs = db.get_runs_by_mode("baseline") or []
    runs = backtest_runs + baseline_runs
    
    if not runs:
        raise HTTPException(status_code=404, detail="No backtest or baseline runs found")
    
    # Group by agent and get latest for each
    latest_by_agent = {}
    for run in runs:
        agent = run['agent_name']
        if agent not in latest_by_agent or run['created_at'] > latest_by_agent[agent]['created_at']:
            latest_by_agent[agent] = run
    
    # Build comparison response
    comparison_runs = []
    for agent, run in latest_by_agent.items():
        equity_data = db.get_equity_curve(run['run_id'])
        equity_data = filter_market_hours(equity_data)
        
        if equity_data:
            comparison_runs.append(EquityCurve(
                run_id=run['run_id'],
                agent_name=agent,
                data=[EquityPoint(**point) for point in equity_data],
                metrics={
                    'total_return': run['total_return'],
                    'sharpe_ratio': run['sharpe_ratio'],
                    'max_drawdown': run['max_drawdown'],
                    'num_trades': run['num_trades']
                }
            ))
    
    if not comparison_runs:
        raise HTTPException(status_code=404, detail="No equity data found")
    
    best_run = max(comparison_runs, key=lambda r: r.metrics['total_return'] or 0)
    
    return ComparisonResponse(
        runs=comparison_runs,
        summary={
            'num_runs': len(comparison_runs),
            'best_performer': best_run.agent_name,
            'best_return': best_run.metrics['total_return']
        }
    )


@app.get("/runs", response_model=List[RunMetadata])
async def get_runs(mode: Optional[str] = None):
    """
    Get all backtest/paper runs.
    
    Query params:
    - mode: 'backtest' or 'paper' (optional)
    """
    if mode:
        runs = db.get_runs_by_mode(mode)
    else:
        runs = db.get_all_runs()
    
    return [RunMetadata(**run) for run in runs]


@app.get("/runs/{run_id}", response_model=RunMetadata)
async def get_run(run_id: str):
    """Get metadata for a specific run."""
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return RunMetadata(**run)


@app.get("/runs/{run_id}/equity", response_model=EquityCurve)
async def get_equity_curve(run_id: str):
    """
    Get equity curve for a specific run.
    
    Returns time-series data with equity, cash, positions_value, daily_return.
    Filtered to market hours only (9:30 AM - 4:00 PM ET).
    """
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    equity_data = db.get_equity_curve(run_id)
    equity_data = filter_market_hours(equity_data)
    
    return EquityCurve(
        run_id=run_id,
        agent_name=run['agent_name'],
        data=[EquityPoint(**point) for point in equity_data],
        metrics={
            'total_return': run['total_return'],
            'sharpe_ratio': run['sharpe_ratio'],
            'max_drawdown': run['max_drawdown'],
            'num_trades': run['num_trades']
        }
    )


@app.get("/compare", response_model=ComparisonResponse)
async def compare_runs(run_ids: str):
    """
    Compare multiple runs.
    
    Query params:
    - run_ids: comma-separated list of run IDs (e.g., "run1,run2,run3")
    
    Returns equity curves for all specified runs, ready for multi-line chart.
    """
    ids = [rid.strip() for rid in run_ids.split(',') if rid.strip()]
    
    if not ids:
        raise HTTPException(status_code=400, detail="At least one run_id required")
    
    runs = []
    final_equities = []
    
    for run_id in ids:
        run = db.get_run(run_id)
        if not run:
            continue
        
        equity_data = db.get_equity_curve(run_id)
        equity_data = filter_market_hours(equity_data)
        if equity_data:
            final_equities.append(run['final_equity'] or 0)
            
            runs.append(EquityCurve(
                run_id=run_id,
                agent_name=run['agent_name'],
                data=[EquityPoint(**point) for point in equity_data],
                metrics={
                    'total_return': run['total_return'],
                    'sharpe_ratio': run['sharpe_ratio'],
                    'max_drawdown': run['max_drawdown'],
                    'num_trades': run['num_trades']
                }
            ))
    
    if not runs:
        raise HTTPException(status_code=404, detail="No data found for specified runs")
    
    # Build summary: identify winner (highest final equity)
    best_run = max(runs, key=lambda r: r.metrics['total_return'] or 0) if runs else None
    
    return ComparisonResponse(
        runs=runs,
        summary={
            'num_runs': len(runs),
            'best_performer': best_run.agent_name if best_run else None,
            'best_return': best_run.metrics['total_return'] if best_run else None
        }
    )


# ============================================================================
# Paper Trading Routes
# ============================================================================

@app.get("/paper/account")
async def get_paper_account():
    """
    Get live paper trading account info from Alpaca.
    
    Returns:
        Account details: cash, equity, buying_power, portfolio_value, etc.
    """
    try:
        client = AlpacaPaperTradingClient()
        account = client.get_account()
        
        if account:
            return {
                "success": True,
                "account": account,
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {
                "success": False,
                "error": "Failed to fetch account",
                "timestamp": datetime.now().isoformat()
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


@app.get("/paper/positions")
async def get_paper_positions():
    """
    Get current positions from Alpaca paper trading account.
    Cached for 30 seconds (prices update frequently).
    
    Returns:
        List of positions: {symbol, qty, avg_fill_price, current_price, unrealized_pl, unrealized_plpc}
    """
    try:
        # Check cache first
        cached = paper_trading_cache.get(CACHE_KEY_POSITIONS)
        if cached:
            return {
                "success": True,
                "count": len(cached),
                "positions": cached,
                "timestamp": datetime.now().isoformat(),
                "cached": True
            }
        
        client = AlpacaPaperTradingClient()
        positions = client.get_positions()
        
        positions_data = [
            {
                "symbol": p.symbol,
                "qty": p.qty,
                "avg_fill_price": p.avg_fill_price,
                "current_price": p.current_price,
                "unrealized_pl": p.unrealized_pl,
                "unrealized_plpc": p.unrealized_plpc,
                "side": p.side,
                "market_value": p.market_value
            }
            for p in positions
        ]
        
        # Cache for 30 seconds
        paper_trading_cache.set(CACHE_KEY_POSITIONS, positions_data, TTL_POSITIONS)
        
        return {
            "success": True,
            "count": len(positions_data),
            "positions": positions_data,
            "timestamp": datetime.now().isoformat(),
            "cached": False
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "positions": [],
            "timestamp": datetime.now().isoformat()
        }


@app.get("/paper/trades")
async def get_paper_trades(limit: int = 50):
    """
    Get recent trades/fills from Alpaca paper trading account.
    Cached for 60 seconds (trade history changes infrequently).
    
    Query params:
    - limit: Max number of trades to return (default 50)
    
    Returns:
        List of trades with symbol, qty, side, price, timestamp
    """
    try:
        # Check cache first
        cached = paper_trading_cache.get(CACHE_KEY_TRADES)
        if cached:
            return {
                "success": True,
                "count": len(cached),
                "trades": cached,
                "timestamp": datetime.now().isoformat(),
                "cached": True
            }
        
        client = AlpacaPaperTradingClient()
        activities = client.get_activities(activity_type="FILL", limit=limit)
        
        trades = []
        for activity in activities:
            trades.append({
                "id": activity.get("id"),
                "symbol": activity.get("symbol"),
                "qty": float(activity.get("qty", 0)),
                "side": activity.get("side"),
                "price": float(activity.get("price", 0)),
                "timestamp": activity.get("created_at"),
                "order_status": activity.get("order_status")
            })
        
        # Cache for 60 seconds
        paper_trading_cache.set(CACHE_KEY_TRADES, trades, TTL_TRADES)
        
        return {
            "success": True,
            "count": len(trades),
            "trades": trades,
            "timestamp": datetime.now().isoformat(),
            "cached": False
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "trades": [],
            "timestamp": datetime.now().isoformat()
        }


@app.get("/paper/portfolio-history")
async def get_paper_portfolio_history(timeframe: str = "1D"):
    """
    Get portfolio history/equity curve from Alpaca.
    Cached for 2 minutes (updated frequently but not every second).
    
    Query params:
    - timeframe: '1D' (day), '1W' (week), '1M' (month), '3M', '1A' (all), 'all'
    
    Returns:
        Dict with equity curve: timestamp, equity for each data point
    """
    try:
        # Check cache first
        cached = paper_trading_cache.get(CACHE_KEY_PORTFOLIO_HISTORY)
        if cached:
            return {
                "success": True,
                "timeframe": timeframe,
                "equity_curve": cached,
                "timestamp": datetime.now().isoformat(),
                "cached": True
            }
        
        client = AlpacaPaperTradingClient()
        history = client.get_portfolio_history(timeframe=timeframe)
        
        if history:
            # Convert timestamps and build equity curve
            equity_curve = []
            
            if "equity" in history and "timestamp" in history:
                for ts, equity in zip(history.get("timestamp", []), history.get("equity", [])):
                    equity_curve.append({
                        "timestamp": datetime.fromtimestamp(ts).isoformat() if isinstance(ts, int) else str(ts),
                        "equity": equity
                    })
            
            # Cache for 2 minutes
            paper_trading_cache.set(CACHE_KEY_PORTFOLIO_HISTORY, equity_curve, TTL_PORTFOLIO_HISTORY)
            
            return {
                "success": True,
                "timeframe": timeframe,
                "equity_curve": equity_curve,
                "base_value": history.get("base_value"),
                "timestamp": datetime.now().isoformat(),
                "cached": False
            }
        else:
            return {
                "success": False,
                "error": "No portfolio history available",
                "equity_curve": [],
                "timestamp": datetime.now().isoformat()
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "equity_curve": [],
            "timestamp": datetime.now().isoformat()
        }


@app.post("/paper/start-session")
async def start_paper_session(agent_name: str = "Agent"):
    """
    Start a new paper trading session and return run_id.
    
    Query params:
    - agent_name: Name of agent/strategy (default: "Agent")
    
    Returns:
        run_id for tracking this session
    """
    try:
        run_id = create_paper_trading_session(agent_name)
        
        # Get current account state
        client = AlpacaPaperTradingClient()
        account = client.get_account()
        
        if account:
            initial_equity = account.get("equity", 100000)
            
            # Create run record in database
            db.insert_run(
                run_id=run_id,
                agent_name=agent_name,
                mode="paper",
                start_date=datetime.now().isoformat(),
                end_date="",
                initial_equity=initial_equity
            )
            
            return {
                "success": True,
                "run_id": run_id,
                "agent_name": agent_name,
                "initial_equity": initial_equity,
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {
                "success": False,
                "error": "Failed to fetch initial account state",
                "timestamp": datetime.now().isoformat()
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


# ============================================================================
# Baseline Routes (for comparing paper trading against benchmarks)
# ============================================================================

@app.get("/paper/baselines")
async def get_paper_baselines(days: int = 31):
    """
    Get baseline equity curves from database (real historical data).
    Pre-computed from same data source as backtesting.
    Cached for 1 hour.
    
    Query params:
    - days: Ignored (uses full history from database)
    
    Returns:
        Dict with 'djia' and 'buy_and_hold' equity curves
    """
    try:
        # Check cache first
        cached = paper_trading_cache.get(CACHE_KEY_BASELINES)
        if cached:
            return {
                "success": True,
                "baselines": cached,
                "timestamp": datetime.now().isoformat(),
                "cached": True,
                "note": "Real historical data (same as backtesting)"
            }
        
        # Fetch from database
        result = get_baselines_from_db()
        
        if result.get("success"):
            baselines = result.get("baselines", {})
            # Cache for 1 hour
            paper_trading_cache.set(CACHE_KEY_BASELINES, baselines, TTL_BASELINES)
            
            return {
                "success": True,
                "baselines": baselines,
                "timestamp": datetime.now().isoformat(),
                "cached": False,
                "note": "Real historical data (same as backtesting)"
            }
        else:
            return {
                "success": False,
                "error": result.get("error", "No baseline data available"),
                "baselines": {},
                "timestamp": datetime.now().isoformat()
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "baselines": {},
            "timestamp": datetime.now().isoformat()
        }


# ============# ============================================================================
# Market Data Routes
# ============================================================================

@app.get("/ticker")
async def get_ticker(symbols: str = "AAPL,NVDA,MSFT,BTC"):
    """
    Get live market quotes for symbols.
    
    Query params:
    - symbols: comma-separated list of symbols (default: AAPL,NVDA,MSFT,BTC)
    
    Returns:
        List of quotes with symbol, price, change%, timestamp
    """
    symbol_list = [s.strip().upper() for s in symbols.split(',') if s.strip()]
    
    if not symbol_list:
        return {"error": "No symbols provided", "quotes": []}
    
    try:
        quotes = get_market_quotes(symbol_list)
        return {
            "success": True,
            "count": len(quotes),
            "quotes": quotes,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "quotes": []
        }


# ============================================================================
# Admin Routes (for testing/debugging)
# ============================================================================

@app.delete("/admin/clear")
async def admin_clear_all():
    """⚠️ Clear all data. Use with caution!"""
    db.clear_all()
    return {"status": "cleared"}


@app.delete("/admin/runs/{run_id}")
async def admin_delete_run(run_id: str):
    """⚠️ Delete a specific run."""
    db.delete_run(run_id)
    return {"status": "deleted", "run_id": run_id}


# ============================================================================
# Static Frontend Routes (must come AFTER API routes to not intercept them)
# ============================================================================

frontend_path = Path(__file__).parent.parent / "frontend"

@app.get("/", include_in_schema=False)
async def serve_root():
    """Serve index.html for root path."""
    return FileResponse(frontend_path / "index.html")

@app.get("/styles.css", include_in_schema=False)
async def serve_styles():
    """Serve styles.css."""
    return FileResponse(frontend_path / "styles.css", media_type="text/css")

@app.get("/app.js", include_in_schema=False)
async def serve_app_js():
    """Serve app.js."""
    return FileResponse(frontend_path / "app.js", media_type="text/javascript")


# ============================================================================
# Run the app
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
