"""
FastAPI backend for agentic trading dashboard.
Serves equity curves, run metadata, and comparison data.

This module is the application composition root: it creates the FastAPI app,
configures middleware, registers routers, wires startup hooks, and serves the
frontend. Backend API route bodies live in ``dashboard.backend.api.routers.*``.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pathlib import Path
import os

# --- Deprecated direct-execution compatibility ---------------------------------
# Canonical startup is:  uvicorn dashboard.backend.app:app
# Running this file directly (``python dashboard/backend/app.py``) is a DEPRECATED
# compatibility path. When executed as a script, Python puts ``dashboard/backend``
# on ``sys.path`` (not the repo root), so the canonical ``dashboard.backend.*``
# imports below would not resolve. Add the repo root to ``sys.path`` in that case
# only. When imported as a package (``uvicorn dashboard.backend.app:app``), this
# block is a no-op and there is no import-path side effect.
if __package__ in (None, ""):
    import sys as _sys

    _REPO_ROOT = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    if _REPO_ROOT not in _sys.path:
        _sys.path.insert(0, _REPO_ROOT)
# -------------------------------------------------------------------------------

from dashboard.backend.database import db, DB_PATH
from dashboard.backend.paths import FRONTEND_DIR
from dashboard.backend.middleware import SessionMiddleware, CSPHeaderMiddleware
from dashboard.backend.api.router import api_router
from dashboard.backend.api.routers.paper_trading import router as paper_trading_router
from dashboard.backend.api.routers.health import router as health_router
from dashboard.backend.api.routers.backtests import router as backtests_router
from dashboard.backend.api.routers.config import router as config_router
from dashboard.backend.api.routers.market import router as market_router
from dashboard.backend.api.routers.admin import router as admin_router
from dashboard.backend.domain.backtesting.baselines.paper import create_paper_baselines_if_not_exists

# Load .env from project root (ANTHROPIC_API_KEY, ALPACA_*)
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_path)
    except ImportError:
        pass

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
    allow_headers=["content-type", "authorization", "x-session-id", "x-browser-id", "x-api-key", "accept"],
    expose_headers=["content-type", "cache-control", "etag", "x-session-id"],
    max_age=3600,
)

# Add session middleware (selective: backtest routes only)
app.add_middleware(SessionMiddleware)

# Versioned REST API (auth, future teams/contest/config)
app.include_router(api_router)

# Paper Trading routes (unprefixed: external paths remain /paper/...)
app.include_router(paper_trading_router)

# Backend API routes (unprefixed: external paths unchanged — /health, /ticker,
# /backtest/*, /api/backtest/*, /runs*, /compare, /config/defaults, /admin/*)
app.include_router(health_router)
app.include_router(backtests_router)
app.include_router(config_router)
app.include_router(market_router)
app.include_router(admin_router)

# CSP Middleware: Permit Chart.js and inline scripts (for development)
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

@app.get("/home-page.js", include_in_schema=False)
async def serve_home_page_js():
    """Serve home-page.js for the Home tab mock live UI."""
    return FileResponse(frontend_path / "home-page.js", media_type="text/javascript")

@app.get("/js/{file_name}", include_in_schema=False)
async def serve_js_module(file_name: str):
    """Serve js/*.js modules (e.g. leaderboard.js)."""
    if not file_name.endswith(".js") or "/" in file_name or "\\" in file_name:
        raise HTTPException(status_code=404, detail="Script not found")

    script_path = (frontend_path / "js" / file_name).resolve()
    js_dir = (frontend_path / "js").resolve()
    if not script_path.is_file() or js_dir not in script_path.parents:
        raise HTTPException(status_code=404, detail="Script not found")

    return FileResponse(script_path, media_type="text/javascript")

@app.get("/market-events/{file_name}", include_in_schema=False)
async def serve_market_events_js(file_name: str):
    """Serve market-events/*.js modules for the Live Market Events panel."""
    if not file_name.endswith(".js") or "/" in file_name or "\\" in file_name:
        raise HTTPException(status_code=404, detail="Script not found")

    script_path = (frontend_path / "market-events" / file_name).resolve()
    market_events_dir = (frontend_path / "market-events").resolve()
    if not script_path.is_file() or market_events_dir not in script_path.parents:
        raise HTTPException(status_code=404, detail="Script not found")

    return FileResponse(script_path, media_type="text/javascript")

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
    # Canonical startup is ``uvicorn dashboard.backend.app:app``. This direct
    # invocation is a deprecated compatibility path; reference the app by its
    # canonical import string so the reloader resolves the same module identity.
    import uvicorn
    uvicorn.run("dashboard.backend.app:app", host="0.0.0.0", port=8000, reload=True)
