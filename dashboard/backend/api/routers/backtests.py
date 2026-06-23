"""Backtest, run, and comparison routes (Phase 3D4A).

Moved verbatim from ``dashboard/backend/app.py``. All external paths
(``/backtest/*``, ``/api/backtest/*``, ``/runs*``, ``/compare``), methods,
endpoint names, response models, market-hours filtering, and the background
backtest workflow are unchanged. This router is registered directly on the app
(routes carry their full absolute paths; no extra prefix is applied), so the
``/api/backtest/...`` paths remain exactly as before.

The decorator order is preserved so that ``/api/backtest/compare/latest`` is
registered before ``/api/backtest/{run_id}`` and ``/runs/latest/metrics`` before
``/runs/{run_id}``.
"""

import threading
from pathlib import Path
from typing import List, Optional

import pytz
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from dashboard.backend.database import db, DB_PATH
from dashboard.backend.paths import DASHBOARD_DIR, REPO_ROOT, SCRIPTS_DIR
from dashboard.backend.middleware import get_session_id_from_request

router = APIRouter()


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
    baseline_djia_run_id: Optional[str] = None
    baseline_buyhold_run_id: Optional[str] = None
    llm_model: Optional[str] = None


class EquityCurve(BaseModel):
    run_id: str
    agent_name: str
    data: List[EquityPoint]
    metrics: dict


class ComparisonResponse(BaseModel):
    runs: List[EquityCurve]
    summary: dict


# ============================================================================
# Background backtest state + worker
# ============================================================================

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

@router.post("/backtest/run")
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

@router.get("/backtest/status")
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

@router.get("/api/backtest/runs", response_model=List[RunMetadata])
async def get_backtest_runs(request: Request):
    """Get all backtest runs for this session."""
    session_id = get_session_id_from_request(request)
    runs = db.get_runs_by_session(session_id)
    runs = [r for r in runs if r['mode'] == 'backtest']
    return [RunMetadata(**run) for run in runs]


# IMPORTANT: Register /compare/latest BEFORE /{run_id} to prevent {run_id} from matching "compare/latest"

@router.get("/api/backtest/compare/latest", response_model=ComparisonResponse)
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


@router.get("/api/backtest/{run_id}", response_model=EquityCurve)
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


@router.get("/runs/latest/metrics", response_model=RunMetadata)
async def get_latest_metrics(request: Request):
    """Get metrics for the latest Agent backtest run in this session (excludes baselines)."""
    session_id = request.state.session_id
    runs = [r for r in db.get_runs_by_session(session_id) or [] 
            if r['mode'] == 'backtest' and r['agent_name'] == 'Agent']
    if not runs:
        raise HTTPException(status_code=404, detail="No Agent backtest runs found for this session")
    
    latest_run = max(runs, key=lambda r: r['created_at'])
    return RunMetadata(**latest_run)


@router.get("/runs", response_model=List[RunMetadata])
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


@router.get("/runs/{run_id}", response_model=RunMetadata)
async def get_run(run_id: str, request: Request):
    """Get metadata for a specific run."""
    session_id = request.state.session_id
    run = db.get_run_with_session(run_id, session_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found or not yours")
    return RunMetadata(**run)


@router.get("/runs/{run_id}/equity", response_model=EquityCurve)
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


@router.get("/compare", response_model=ComparisonResponse)
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
