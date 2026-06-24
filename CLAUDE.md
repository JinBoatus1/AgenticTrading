# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

**Agentic Trading Lab** — an open-source platform for LLM-powered trading agents (backtests, live paper trading, decision-log inspection, leaderboards). The live app is `dashboard/`; everything else is supporting (docs, a PyPI client, and an imported research framework).

The repo is **two loosely-coupled subsystems**:

- **`dashboard/`** — the shipping product. FastAPI backend + static frontend + backtest CLIs. This is where almost all day-to-day work happens.
- **`orchestration/`** — the *FinAgent Orchestration Framework* (multi-agent DAG planner, agent pools, Neo4j/vector memory), imported research code from the NeurIPS 2025 paper by Jifeng Li et al. It is largely self-contained, has hardcoded absolute conda paths (e.g. `orchestration/run_orchestrator.sh`), and is **not** wired into the dashboard. Treat it as a separate project unless explicitly asked.

## Critical: backend uses flat top-level imports

`dashboard/backend/` is **not a Python package** — there is no `__init__.py` at the backend root, and modules import each other by bare name (`from database import db`, `from app import app`, `from paths import ...`). Subpackages (`api/`, `engines/`, `services/`, `tests/`) *do* have `__init__.py`.

Consequences:
- The backend must run with `dashboard/backend/` on `sys.path` (i.e. as the working directory). This is why the Dockerfile/`render.yaml` invoke `python dashboard/backend/app.py` rather than `uvicorn` with a module path.
- Tests prepend the backend dir to `sys.path` themselves: `sys.path.insert(0, str(Path(__file__).parent.parent))` then `from app import app`.
- Do not "fix" these into package-relative imports — it would break the run command across Docker/Render.

## Common commands

All backend commands assume you are **inside `dashboard/backend/`**.

```bash
# Install deps (the real dependency file — NOT root pyproject.toml)
pip install -r requirements.txt        # run from repo root

# Run the backend + dashboard locally (serves frontend at http://localhost:8000)
cd dashboard/backend && python app.py  # uvicorn with reload, port 8000

# Run tests (pytest; not declared as a dep — pip install pytest first)
cd dashboard/backend && pytest tests/ -v
cd dashboard/backend && pytest tests/test_llm_validator.py -v        # single file
cd dashboard/backend && pytest tests/test_auth.py::test_name -v       # single test

# Backtest CLIs (the heavy lifting lives here, run from backend dir)
cd dashboard/backend && python ../scripts/backtest_hourly_agent.py    # main hourly agent backtest
```

Docs (Sphinx / Read the Docs), from repo root:
```bash
pip install -r requirements-sphinx.txt
cd docs/source && sphinx-autobuild . ../build --open-browser --port 8000
```

## Environment & credentials

- `app.py` loads `.env` from **`dashboard/.env`** (`Path(__file__).resolve().parent.parent / ".env"`), not the repo root — put your env file there. `.env.example` (at repo root) lists the keys: `ALPACA_API_KEY`/`ALPACA_SECRET_KEY` (paper API) and optionally `ANTHROPIC_API_KEY`/`OPENAI_API_KEY`/`DEEPSEEK_API_KEY`.
- `DATABASE_PATH` overrides the SQLite location (defaults to `dashboard/storage/data/backtest.db`; Render mounts a persistent disk at `/data`).
- Alpaca paper-trading credentials also live in `credentials/alpaca.json` (gitignored; see `credentials/alpaca.json.example`).

## Architecture

Pipeline is **backtest → SQLite → API → dashboard**.

- **Backtest engines** (`dashboard/scripts/`): standalone CLI scripts that fetch Alpaca hourly bars, run agent + baseline logic, and write runs into SQLite. `backtest_hourly_agent.py` is the canonical/largest one; `external_backtest_service.py` reuses its engine classes. Each backtest typically writes multiple runs (agent + buy-and-hold + index baseline).
- **Persistence** (`dashboard/backend/database.py`): a thin `BacktestDatabase` SQLite wrapper. Schema is created on first use and **self-migrates** (`_init_schema` + `_migrate_schema`) — when changing the schema, update both. Session isolation is via a `session_id` column on `agent_runs`; equity/trades inherit ownership through their run.
- **API** (`dashboard/backend/app.py`): FastAPI with **two coexisting route surfaces** —
  1. Legacy flat routes registered directly on `app`: `/health`, `/runs`, `/runs/{id}/equity`, `/compare`, `/backtest/run`, `/paper/*`, `/ticker`, `/config/defaults`, plus static frontend serving at `/`.
  2. Versioned router under `/api` (`api/router.py` → `api/{auth,agents,algo,external_backtest,leaderboard,health}.py`).
  Equity series are filtered to US market hours via `filter_market_hours()` before being returned.
- **Frontend** (`dashboard/frontend/`): vanilla JS + Chart.js, no build step. `app.js`, `home-page.js`, `js/leaderboard.js`, `market-events/`. Served by the backend in local/Render runs; also deployed as a static site to Vercel (`vercel.json` rewrites all paths to `index.html`).
- **Paths** (`dashboard/backend/paths.py`): single source of truth for all on-disk locations — use these constants instead of recomputing paths.

### Baseline strategies (registry pattern)

`dashboard/backend/engines/strategies/` holds benchmark strategies (`buy_hold`, `equal_weight_index`, `equal_weight_buyhold`, `market_index`, `mean_variance`). To add one: subclass `BaselineStrategy` (`base.py`), give it a `key`, and add the class to `_STRATEGY_CLASSES` in `registry.py`. `get_strategy(config)` resolves by `strategy`/`type` key (with back-compat `_ALIASES`). Nothing else needs editing.

### LLM safety boundary

`llm_validator.py` is a hard security boundary: LLM trading responses must be JSON-only matching the trading schema — `tool_calls`/`function_calls` are rejected, portfolio constraints enforced, decisions logged. `llm_integration_example.py` shows the intended endpoint shape. See `dashboard/backend/SECURITY.md`. Do not loosen this to allow tool/web access from agent responses.

### External agents & "My Trading Algo"

- **External agents** (`api/agents.py`, `agent_store.py`): users register an agent to get an API key (`ag_<token>`, stored as a SHA-256 hash). The agent then drives an hourly backtest step-by-step over HTTP — each trading hour the server waits for `POST /decisions` up to a timeout, otherwise auto-holds (`external_backtest_service.py`). Client example: `dashboard/examples/external_agent_client.py`.
- **My Trading Algo** (`algo_service.py`, `api/algo.py`): real LLM chat that assembles a strategy from blocks and runs an Alpaca hourly backtest via subprocess.

## Deployment

- **Backend** → Render (`render.yaml`): `python dashboard/backend/app.py`, Python 3.13, persistent disk at `/data`, health check `/health`. Public instance: `https://agentictrading.onrender.com`.
- **Frontend** → Vercel (`vercel.json`): static `dashboard/frontend`. Live: `https://agentic-trading-lab.vercel.app/`.
- **PyPI client** (`packaging/agentictrading/`): standalone, dependency-free (stdlib-only) Python client for the REST API. Published via `.github/workflows/publish-pypi.yml` on `v*` tags using PyPI Trusted Publishing; the workflow asserts the tag matches `__version__`. See `packaging/agentictrading/RELEASING.md`.

## Gotchas

- Root `pyproject.toml` (`finagent-orchestration`, deps `a2a-sdk`/`mcp`) is for the orchestration subsystem, **not** the dashboard — don't add dashboard deps there; edit `requirements.txt`.
- `README.md`'s "File Structure" diagram is idealized (`backend/`, `frontend/`, `data/` at root). The real layout nests everything under `dashboard/` and data under `dashboard/storage/`.
- The committed `dashboard/storage/data/backtest.db` holds seed runs referenced by `dashboard/config/defaults.json` (`defaultRuns` IDs). The frontend falls back to these when no session runs exist; if you regenerate the DB, update `defaults.json` to match.
- Pytest is not in `requirements.txt`; install it separately before running tests.
