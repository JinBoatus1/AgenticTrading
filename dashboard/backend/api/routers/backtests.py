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

import re
import threading
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import List, Optional

import pytz
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

# matplotlib is imported and configured (headless Agg backend) once at module
# import, not per request: the plot endpoint previously re-imported it and
# re-called matplotlib.use("Agg") on every call. Agg must be selected before any
# pyplot import elsewhere in the process, so it belongs at module scope.
import matplotlib
matplotlib.use("Agg")

from dashboard.backend.database import db, DB_PATH
from dashboard.backend.paths import DASHBOARD_DIR, REPO_ROOT, SCRIPTS_DIR
from dashboard.backend.middleware import get_session_id_from_request
from dashboard.backend.api.rate_limit import FixedWindowRateLimiter, client_key
from dashboard.backend.domain.agents.service import agent_service
from dashboard.backend.equity_plot import (
    curve_timestamps_and_values,
    market_index_baselines_for_run,
    render_backtest_equity_png,
)

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

def run_backtest_background(
    start_date: str,
    end_date: str,
    session_id: str,
    strategy_prompt: Optional[str] = None,
    model: Optional[str] = None,
):
    """Run backtest in background thread."""
    global backtest_status, backtest_session_id

    strategy_prompt_path = None
    try:
        import subprocess
        import sys
        import os
        import tempfile
        
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
        
        cmd = [
            python_exe, str(script_path),
            "--start", start_date, "--end", end_date,
            "--session-id", session_id,
            "--use-llm",  # Enable LLM for real agent trading
        ]

        # Optional free-form strategy prompt: written to a temp file (avoids
        # shell-escaping a long prompt) and passed via --strategy-prompt-file.
        if strategy_prompt and strategy_prompt.strip():
            fd, strategy_prompt_path = tempfile.mkstemp(prefix="strategy_prompt_", suffix=".txt")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(strategy_prompt.strip())
            cmd += ["--strategy-prompt-file", strategy_prompt_path]

        if model and model.strip():
            cmd += ["--model", model.strip()]

        print(f"📋 Running: {' '.join(cmd)}", flush=True)
        
        result = subprocess.run(
            cmd,
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
        if strategy_prompt_path:
            try:
                import os
                os.remove(strategy_prompt_path)
            except OSError:
                pass
        print(f"✋ Backtest background thread finished", flush=True)

class BacktestRunRequest(BaseModel):
    """Optional JSON body for POST /backtest/run.

    All fields are optional; when present they override the query-param
    defaults. ``strategy_prompt`` is a free-form strategy that REPLACES the
    built-in agent prompt for this run, and ``model`` overrides the LLM model id.
    ``agent_id`` targets a built-in agent's trading session (Discord / website).
    Long prompts belong in the body (not the query string).
    """
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    strategy_prompt: Optional[str] = None
    model: Optional[str] = None
    agent_id: Optional[str] = None


# /backtest/run spends real operator LLM credits per trading hour of the run, on
# an anonymous (session-id-only) surface. The params arrive as EITHER query
# params or a JSON body, so validation runs on the merged effective values in the
# handler rather than only on the Pydantic body.
MAX_STRATEGY_PROMPT_CHARS = 4000
MAX_BACKTEST_DAYS = 31

# A model id is a provider/model slug: letters, digits, and . _ / - only, bounded
# length. This rejects a garbage/injection string reaching the backtest subprocess
# — it deliberately does NOT gate model *tier*: the dashboard UI intentionally
# offers expensive models (e.g. claude-opus), so tiering is a product/auth decision,
# not enforced here, and gating by the pricing table would 422 the UI's own options.
_MODEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/\-]{0,63}$")

# Per-client run budget: a best-effort throttle only. The global
# ``backtest_status["running"]`` flag blocks *concurrent* runs; this throttles
# *serial* abuse from a well-behaved client. A client rotating its self-minted
# session id can evade it (see api/rate_limit) — the per-request caps above
# (model shape, prompt length, date range) are the hard limits.
_backtest_rate_limiter = FixedWindowRateLimiter(max_events=10, window_seconds=3600)


def _parse_ymd(value: str, field: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail=f"{field} must be a date in YYYY-MM-DD format.")


def _validate_backtest_params(start_date, end_date, strategy_prompt, model) -> None:
    """Reject malformed / cost-abuse inputs before scheduling the background run.

    - ``model`` must look like a model id (charset + length), which rejects an
      arbitrary/garbage string reaching the backtest subprocess. It does NOT cap
      model tier (the UI intentionally offers expensive models).
    - ``strategy_prompt`` is length-capped (it is injected into every LLM call).
    - the date range must be well-formed and bounded (each extra day is more
      hourly LLM calls).
    """
    if model and not _MODEL_ID_RE.match(model.strip()):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid model id '{model}'.",
        )
    if strategy_prompt and len(strategy_prompt) > MAX_STRATEGY_PROMPT_CHARS:
        raise HTTPException(
            status_code=422,
            detail=f"strategy_prompt too long (max {MAX_STRATEGY_PROMPT_CHARS} characters).",
        )
    start = _parse_ymd(start_date, "start_date")
    end = _parse_ymd(end_date, "end_date")
    if end < start:
        raise HTTPException(status_code=422, detail="end_date must not be before start_date.")
    if (end - start).days > MAX_BACKTEST_DAYS:
        raise HTTPException(
            status_code=422,
            detail=f"Date range too large (max {MAX_BACKTEST_DAYS} days).",
        )


def _resolve_backtest_session(request: Request, agent_id: Optional[str]) -> str:
    """Return the session that should own this backtest run.

    When ``agent_id`` references a built-in agent, use that agent's session so
    results appear on its website card (without exposing ``session_id`` in public
    listings). Otherwise fall back to the caller's ``X-Session-Id``.
    """
    if not agent_id:
        return request.state.session_id
    agent = agent_service.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if (agent.get("agent_type") or "external") != "builtin":
        raise HTTPException(
            status_code=422,
            detail="agent_id must reference a built-in agent",
        )
    return agent["session_id"]


@router.post("/backtest/run")
async def run_backtest_endpoint(
    request: Request,
    start_date: str = "2026-05-01",
    end_date: str = "2026-05-07",
    strategy_prompt: Optional[str] = None,
    model: Optional[str] = None,
    body: Optional[BacktestRunRequest] = None,
):
    """
    Trigger backtest in background (non-blocking).
    
    Returns immediately with status. Check /backtest/status to monitor progress.

    Accepts an optional JSON body (preferred for a long ``strategy_prompt``);
    body fields override the equivalent query params. Backward compatible with
    callers that pass only ``start_date``/``end_date`` as query params.
    """
    # Body (when provided) overrides query params.
    agent_id: Optional[str] = None
    if body is not None:
        start_date = body.start_date or start_date
        end_date = body.end_date or end_date
        strategy_prompt = body.strategy_prompt or strategy_prompt
        model = body.model or model
        agent_id = body.agent_id

    # Guard operator LLM spend BEFORE scheduling anything. Validation first (so a
    # caller correcting a bad request isn't charged rate budget for a typo), then
    # the per-client run budget.
    _validate_backtest_params(start_date, end_date, strategy_prompt, model)
    if not _backtest_rate_limiter.allow(client_key(request)):
        raise HTTPException(
            status_code=429,
            detail="Too many backtests started recently; please try again later.",
        )

    session_id = _resolve_backtest_session(request, agent_id)
    print(f"📌 /backtest/run endpoint called: start_date={start_date}, end_date={end_date}", flush=True)
    print(f"   Session: {session_id[:8]}...", flush=True)
    if strategy_prompt:
        print(f"   Custom strategy prompt: {len(strategy_prompt)} chars", flush=True)
    if model:
        print(f"   Model override: {model}", flush=True)
    
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
        args=(start_date, end_date, session_id, strategy_prompt, model),
        daemon=True
    )
    thread.start()
    
    return {
        "success": True,
        "message": "Backtest started in background. Check /backtest/status for progress.",
        "status_url": "/backtest/status",
        "session_id": session_id,
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


@router.get("/runs/{run_id}/plot.png", include_in_schema=False)
def get_run_plot(run_id: str):
    """Render an equity-curve comparison PNG (agent vs baselines) for a run.

    Public endpoint: the path ends in ``.png`` so it is exempt from the session
    middleware. Used by the Discord bot to post a chart after a backtest, and
    usable directly as an <img> src. Uses the gapless market-hour axis from
    ``docs/examples/simple_trading_agent_backtest.py`` with Playground colors.

    Sync ``def`` so FastAPI runs the CPU-bound matplotlib render in its
    threadpool rather than blocking the event loop; the PNG is cached per run_id.
    """
    return Response(content=_render_run_plot_png(run_id), media_type="image/png")


@lru_cache(maxsize=128)
def _render_run_plot_png(run_id: str) -> bytes:
    """Render (and memoize) the equity-curve comparison PNG for ``run_id``.

    A run's equity data is immutable once written and run_ids are unique per
    run, so the rendered bytes are reused without re-querying the DB or
    re-rendering. HTTPExceptions (missing run / no equity data) are raised, not
    cached — so data that appears later is still picked up on a retry.
    """
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    agent_label = run.get("agent_name") or "Agent"
    agent_curve = filter_market_hours(db.get_equity_curve(run_id))
    timestamps, agent_values = curve_timestamps_and_values(agent_curve)
    if not timestamps:
        raise HTTPException(status_code=404, detail="No equity data to plot for this run")

    initial_capital = float(run.get("initial_equity") or agent_values[0] or 100_000)
    baselines = market_index_baselines_for_run(
        timestamps,
        run.get("start_date") or "",
        run.get("end_date") or "",
        initial_capital,
    )

    try:
        return render_backtest_equity_png(
            agent_label=agent_label,
            agent_run_id=run_id,
            timestamps=timestamps,
            agent_values=agent_values,
            baselines=baselines,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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
