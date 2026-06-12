"""
FastAPI backend for agentic trading dashboard.
Serves equity curves, run metadata, and comparison data.
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
import json
import os
from database import db, DB_PATH
from paths import CONFIG_DIR, DASHBOARD_DIR, FRONTEND_DIR, REPO_ROOT, SCRIPTS_DIR
from market_data import get_market_quotes
from middleware import SessionMiddleware, get_session_id_from_request
from api.router import api_router
from paper_trading import AlpacaPaperTradingClient, create_paper_trading_session
from paper_baselines import create_paper_baselines_if_not_exists
from baselines_endpoint import get_baselines_from_db
from cache import paper_trading_cache, CACHE_KEY_ACCOUNT, CACHE_KEY_POSITIONS, CACHE_KEY_TRADES, CACHE_KEY_PORTFOLIO_HISTORY, CACHE_KEY_BASELINES, TTL_ACCOUNT, TTL_POSITIONS, TTL_TRADES, TTL_PORTFOLIO_HISTORY, TTL_BASELINES
import pytz

# Load .env from project root (ANTHROPIC_API_KEY, ALPACA_*)
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_path)
    except ImportError:
        pass

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
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["content-type", "authorization", "x-session-id", "accept"],  # Lowercase headers
    expose_headers=["content-type", "cache-control", "etag", "x-session-id"],
    max_age=3600,
)

# Add session middleware (selective: backtest routes only)
app.add_middleware(SessionMiddleware)

# Versioned REST API (auth, future teams/contest/config)
app.include_router(api_router)

# CSP Middleware: Permit Chart.js and inline scripts (for development)
from starlette.middleware.base import BaseHTTPMiddleware

class CSPHeaderMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        # Allow Chart.js and scripts from same origin, plus unsafe-inline for development
        response.headers["Content-Security-Policy"] = "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline'; connect-src *; img-src * data:;"
        # DO NOT override CORS headers here — let CORSMiddleware handle them
        return response

app.add_middleware(CSPHeaderMiddleware)

# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize API server."""
    import os
    from pathlib import Path
    import sqlite3
    
    print("🚀 Starting API server...")
    
    # DEBUG: Database location
    print("\n=== 📂 DATABASE DEBUG ===")
    print(f"CWD: {os.getcwd()}")
    print(f"Database path: {DB_PATH}")
    print(f"Database exists: {DB_PATH.exists()}")
    
    # Check database content
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM agent_runs")
            count = cursor.fetchone()[0]
            print(f"✅ Database has {count} runs")
            
            if count > 0:
                cursor.execute("SELECT run_id, agent_name FROM agent_runs LIMIT 3")
                print("Sample runs:")
                for row in cursor.fetchall():
                    print(f"  • {row[0]}: {row[1]}")
            conn.close()
        except Exception as e:
            print(f"❌ Database error: {e}")
    else:
        print("❌ Database NOT FOUND")
    
    print("=== END DATABASE DEBUG ===")
    
    # Also check database directly
    print("\nDirect database check at startup:")
    try:
        import sqlite3
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM agent_runs")
        count = cursor.fetchone()[0]
        cursor.execute("SELECT run_id, session_id FROM agent_runs LIMIT 3")
        rows = cursor.fetchall()
        print(f"Total runs: {count}")
        for run_id, session_id in rows:
            print(f"  - {run_id}: session={session_id}")
        conn.close()
    except Exception as e:
        print(f"Error: {e}")
    print()
    
    print("📊 Backtesting: LLM-powered agent via dashboard/scripts/backtest_hourly_agent.py")
    if os.getenv("ANTHROPIC_API_KEY"):
        print("✅ ANTHROPIC_API_KEY detected - LLM trading enabled")
    else:
        print("⚠️ ANTHROPIC_API_KEY not set - LLM trading disabled")
    print("📊 Paper Trading: Baselines initialized on startup...")
    
    # Initialize paper trading baselines (non-blocking)
    import threading
    
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


import threading

# Global state for background backtest
backtest_status = {"running": False, "error": None, "runs_count": 0}
backtest_session_id = None  # Track which session owns the running backtest

def run_backtest_background(start_date: str, end_date: str, session_id: str):
    """Run backtest in background thread."""
    global backtest_status, backtest_session_id
    
    try:
        import subprocess
        import sys
        import os
        
        backtest_status["running"] = True
        backtest_status["error"] = None
        backtest_session_id = session_id  # Store session for status polling
        
        print(f"🚀 Background: Running backtest: {start_date} to {end_date}", flush=True)
        print(f"   Session: {session_id[:8]}...", flush=True)
        
        backend_dir = Path(__file__).parent.resolve()
        script_path = SCRIPTS_DIR / "backtest_hourly_agent.py"
        db_path = DB_PATH
        venv_dir = REPO_ROOT / ".venv"
        
        # Determine the Python executable to use (from venv if available)
        if venv_dir.exists():
            python_exe = str(venv_dir / "bin" / "python3")
            print(f"🐍 Using venv Python: {python_exe}", flush=True)
        else:
            python_exe = sys.executable
            print(f"🐍 Using system Python: {python_exe}", flush=True)
        
        # Check database directory
        print(f"📁 Database path: {db_path}", flush=True)
        print(f"📁 Database dir exists: {db_path.parent.exists()}", flush=True)
        print(f"📁 Can write to {db_path.parent}: {os.access(db_path.parent, os.W_OK)}", flush=True)
        
        # Run backtest script with LLM enabled
        # Set environment variables for LLM
        env = os.environ.copy()
        if "ANTHROPIC_API_KEY" not in env:
            print("⚠️ Warning: ANTHROPIC_API_KEY not set, LLM will be disabled", flush=True)
        else:
            print(f"✅ ANTHROPIC_API_KEY is set, LLM enabled", flush=True)
        
        print(f"📋 Running: {python_exe} {script_path} --start {start_date} --end {end_date} --session-id {session_id} --use-llm", flush=True)
        
        result = subprocess.run(
            [python_exe, str(script_path),
             "--start", start_date, "--end", end_date,
             "--session-id", session_id,
             "--use-llm"],  # Enable LLM for real agent trading
            cwd=str(DASHBOARD_DIR),
            capture_output=True,
            text=True,
            timeout=1800,  # 30 minutes for LLM backtest (longer than rule-based)
            env=env
        )
        
        # Print script output for debugging
        print(f"\n📋 === BACKTEST SCRIPT OUTPUT ===", flush=True)
        if result.stdout:
            print(f"STDOUT:\n{result.stdout}", flush=True)
        if result.stderr:
            print(f"STDERR:\n{result.stderr}", flush=True)
        print(f"Return code: {result.returncode}", flush=True)
        print(f"=== END BACKTEST OUTPUT ===", flush=True)
        
        if result.returncode != 0:
            error_msg = result.stderr if result.stderr else result.stdout
            backtest_status["error"] = f"Backtest failed with return code {result.returncode}. {error_msg[-500:]}"
            print(f"❌ Backtest failed (returncode={result.returncode})", flush=True)
        else:
            runs = db.get_runs_by_mode("backtest")
            backtest_status["runs_count"] = len(runs)
            print(f"✅ Backtest completed. Found {len(runs)} runs in database.", flush=True)
            if len(runs) > 0:
                print(f"   Latest run IDs: {[r['run_id'] for r in runs[:3]]}", flush=True)
    except Exception as e:
        backtest_status["error"] = str(e)
        print(f"❌ Backtest exception: {e}", flush=True)
    finally:
        backtest_status["running"] = False
        print(f"✋ Backtest background thread finished", flush=True)

@app.post("/backtest/run")
async def run_backtest_endpoint(request: Request, start_date: str = "2026-04-15", end_date: str = "2026-04-23"):
    """
    Trigger backtest in background (non-blocking).
    
    Returns immediately with status. Check /backtest/status to monitor progress.
    """
    session_id = request.state.session_id
    print(f"📌 /backtest/run endpoint called: start_date={start_date}, end_date={end_date}", flush=True)
    print(f"   Session: {session_id[:8]}...", flush=True)
    
    if backtest_status["running"]:
        print(f"⚠️ Backtest already running, rejecting request", flush=True)
        return {
            "success": False,
            "error": "Backtest already running. Please wait for it to complete."
        }
    
    # Start backtest in background thread
    print(f"🧵 Starting background thread for backtest", flush=True)
    thread = threading.Thread(
        target=run_backtest_background,
        args=(start_date, end_date, session_id),  # Pass session_id
        daemon=True
    )
    thread.start()
    
    return {
        "success": True,
        "message": "Backtest started in background. Check /backtest/status for progress.",
        "status_url": "/backtest/status"
    }

@app.get("/backtest/status")
async def get_backtest_status(request: Request):
    """Get backtest status (running, error, or completed)."""
    session_id = request.state.session_id
    
    if backtest_status["running"]:
        return {
            "running": True,
            "message": "Backtest is running... (may take 2-5 minutes)"
        }
    elif backtest_status["error"]:
        return {
            "running": False,
            "error": backtest_status["error"],
            "message": "Backtest failed"
        }
    elif backtest_status["runs_count"] > 0:
        # Verify the completed backtest belongs to this session
        runs = db.get_runs_by_session(session_id)
        if not runs:
            return {
                "running": False,
                "error": "Backtest completed but no runs found for this session",
                "message": "Session mismatch"
            }
        
        return {
            "running": False,
            "success": True,
            "runs_count": backtest_status["runs_count"],
            "session_id": session_id,
            "message": "Backtest completed successfully"
        }
    else:
        return {
            "running": False,
            "message": "No backtest has been run yet"
        }


# ============================================================================
# Backtest Routes
# ============================================================================

@app.get("/api/backtest/runs", response_model=List[RunMetadata])
async def get_backtest_runs(request: Request):
    """Get all backtest runs for this session."""
    session_id = get_session_id_from_request(request)
    runs = db.get_runs_by_session(session_id)
    runs = [r for r in runs if r['mode'] == 'backtest']
    return [RunMetadata(**run) for run in runs]


# IMPORTANT: Register /compare/latest BEFORE /{run_id} to prevent {run_id} from matching "compare/latest"

@app.get("/api/backtest/compare/latest", response_model=ComparisonResponse)
async def compare_latest_backtests(request: Request):
    """Compare the latest backtest runs + baselines for this session."""
    session_id = get_session_id_from_request(request)
    
    # Get this session's runs
    all_runs = db.get_runs_by_session(session_id) or []
    backtest_runs = [r for r in all_runs if r['mode'] == 'backtest']
    baseline_runs = [r for r in all_runs if r['mode'] == 'baseline']
    runs = backtest_runs + baseline_runs
    
    if not runs:
        raise HTTPException(status_code=404, detail="No backtest or baseline runs found for this session")
    
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
        raise HTTPException(status_code=404, detail="No equity data found for session")
    
    best_run = max(comparison_runs, key=lambda r: r.metrics['total_return'] or 0)
    
    return ComparisonResponse(
        runs=comparison_runs,
        summary={
            'num_runs': len(comparison_runs),
            'best_performer': best_run.agent_name,
            'best_return': best_run.metrics['total_return']
        }
    )


@app.get("/api/backtest/{run_id}", response_model=EquityCurve)
async def get_backtest_run(run_id: str, request: Request):
    """Get specific backtest run with equity curve."""
    session_id = get_session_id_from_request(request)
    run = db.get_run_with_session(run_id, session_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found or not yours")
    
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


@app.get("/runs/latest/metrics", response_model=RunMetadata)
async def get_latest_metrics(request: Request):
    """Get metrics for the latest Agent backtest run in this session (excludes baselines)."""
    session_id = request.state.session_id
    runs = [r for r in db.get_runs_by_session(session_id) or [] 
            if r['mode'] == 'backtest' and r['agent_name'] == 'Agent']
    if not runs:
        raise HTTPException(status_code=404, detail="No Agent backtest runs found for this session")
    
    latest_run = max(runs, key=lambda r: r['created_at'])
    return RunMetadata(**latest_run)


@app.get("/runs", response_model=List[RunMetadata])
async def get_runs(request: Request, mode: Optional[str] = None):
    """
    Get all backtest runs (public, not filtered by session).
    Backtest results are meant to be shared/viewed, not isolated per user.
    
    Query params:
    - mode: 'backtest' or 'paper' (optional)
    """
    # Get ALL runs - backtest results are public
    all_runs = db.get_all_runs()
    
    if mode:
        runs = [r for r in all_runs if r['mode'] == mode]
    else:
        # Default: backtest runs only
        runs = [r for r in all_runs if r['mode'] == 'backtest']
    
    print(f"\n📍 /runs: returning {len(runs)} backtest runs")
    
    return [RunMetadata(**run) for run in runs]


@app.get("/runs/{run_id}", response_model=RunMetadata)
async def get_run(run_id: str, request: Request):
    """Get metadata for a specific run."""
    session_id = request.state.session_id
    run = db.get_run_with_session(run_id, session_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found or not yours")
    return RunMetadata(**run)


@app.get("/runs/{run_id}/equity", response_model=EquityCurve)
async def get_equity_curve(run_id: str, request: Request):
    """
    Get equity curve for a specific run.
    
    Returns time-series data with equity, cash, positions_value, daily_return.
    Filtered to market hours only (9:30 AM - 4:00 PM ET).
    """
    session_id = request.state.session_id
    run = db.get_run_with_session(run_id, session_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found or not yours")
    
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
async def compare_runs(run_ids: str, request: Request):
    """
    Compare multiple runs (public, not filtered by session).
    
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
        # Get run without session filter - backtest results are public
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
# Default Configuration Routes
# ============================================================================

@app.get("/config/defaults")
async def get_defaults():
    """
    Get default configuration for the website.
    
    Returns:
        Default run IDs and settings for initial page load
    """
    defaults_path = CONFIG_DIR / "defaults.json"
    
    if not defaults_path.exists():
        return {
            "error": "No defaults configured",
            "message": "Create dashboard/config/defaults.json to set default runs and settings"
        }
    
    import json
    with open(defaults_path, 'r') as f:
        defaults = json.load(f)
    
    return defaults


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
async def admin_delete_run(run_id: str, request: Request):
    """⚠️ Delete a specific run (must be owned by session)."""
    session_id = request.state.session_id
    
    # Verify ownership before deleting
    run = db.get_run_with_session(run_id, session_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found or not yours")
    
    db.delete_run(run_id)
    return {"status": "deleted", "run_id": run_id}


# ============================================================================
# Static Frontend Routes (must come AFTER API routes to not intercept them)
# ============================================================================

frontend_path = FRONTEND_DIR

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

@app.get("/images/{file_name}", include_in_schema=False)
async def serve_image(file_name: str):
    """Serve image files from the images directory."""
    image_path = frontend_path / "images" / file_name
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    
    # Determine media type based on file extension
    ext = image_path.suffix.lower()
    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".svg": "image/svg+xml",
    }
    media_type = media_types.get(ext, "application/octet-stream")
    
    return FileResponse(image_path, media_type=media_type)


# ============================================================================
# Run the app
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
