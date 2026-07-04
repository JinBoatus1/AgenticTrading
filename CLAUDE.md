# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Packaging contract (this branch).** This branch restructured the backend from
> flat top-level modules into the **`dashboard.backend` Python package**. This
> `CLAUDE.md` documents that packaged contract. It intentionally **supersedes** the
> older flat-imports `CLAUDE.md` on `main` — when this merges, take **this** version
> (that older guidance describes code that no longer exists here). See
> `docs/architecture/dashboard-target-structure.md` for the full layout.

## What this repo is

**Agentic Trading Lab** — an open-source platform for LLM-powered trading agents (backtests, live paper trading, decision-log inspection, leaderboards). The live app is `dashboard/`; everything else is supporting (docs, a PyPI client, and an imported research framework).

The repo is **two loosely-coupled subsystems**:

- **`dashboard/`** — the shipping product. FastAPI backend + static frontend + backtest CLIs. This is where almost all day-to-day work happens.
- **`orchestration/`** — the *FinAgent Orchestration Framework* (imported research code from the NeurIPS 2025 paper). Largely self-contained, hardcoded absolute conda paths, **not** wired into the dashboard. Treat it as a separate project unless explicitly asked.

## Critical: the backend is the `dashboard.backend` package

`dashboard/backend/` is a proper Python package: modules import each other by **full package path** — `from dashboard.backend.database import db`, `from dashboard.backend.app import app`, `from dashboard.backend.paths import ...`. The repo root must be on `sys.path` (it is, when you run from the repo root or via `uvicorn`/`python -m`).

Consequences:
- **Run the app** with the app referenced by its import string, from the repo root — never by running the file directly. `python dashboard/backend/app.py` does **not** work (the top-level `dashboard.backend.*` imports fail without the repo root on `sys.path`).
- `app.py` has a `__main__` block that calls `uvicorn.run("dashboard.backend.app:app", …)` — a real `python -m dashboard.backend.app` entrypoint that references the app by canonical import string so the reloader keeps one module identity.
- Domain logic lives under `dashboard/backend/domain/<area>/` and must **not** import `api/` or `app.py` (enforced by `tests/test_architecture_boundaries.py`).

## Common commands

Run from the **repo root** unless noted.

```bash
# Install deps (the real dependency file — NOT root pyproject.toml)
pip install -r requirements.txt

# Run the backend + dashboard locally (serves frontend at http://localhost:8000)
uvicorn dashboard.backend.app:app --reload          # canonical
python -m dashboard.backend.app                       # equivalent module entrypoint

# Run tests (pytest; install it first — not in requirements.txt)
pytest dashboard/backend/tests/ -v
pytest dashboard/backend/tests/test_protocol_api.py -v            # single file
# The PyPI SDK has its own suite:
pytest packaging/agentictrading/tests/ -v

# Backtest CLIs (from the repo root)
python dashboard/scripts/backtest_hourly_agent.py     # main hourly agent backtest
```

`tests/conftest.py` points `DATABASE_PATH` at a temp file before any backend import, so tests never touch the committed `dashboard/storage/data/backtest.db`.

## Environment & credentials

- `app.py` loads `.env` from **`dashboard/.env`**, not the repo root. `.env.example` (repo root) lists the keys: `ALPACA_API_KEY`/`ALPACA_SECRET_KEY` (paper API) and optionally `ANTHROPIC_API_KEY`/`COMMONSTACK_API_KEY`/`OPENAI_API_KEY`/`DEEPSEEK_API_KEY`.
- `DATABASE_PATH` overrides the SQLite location (defaults to `dashboard/storage/data/backtest.db`; Render mounts a persistent disk at `/data`). Persisted stores (protocol runs, strategies) live in this DB.
- Alpaca paper-trading credentials also live in `credentials/alpaca.json` (gitignored; see `credentials/alpaca.json.example`).

## Architecture

Pipeline is **backtest → SQLite → API → dashboard**. The backend is layered (see `docs/architecture/dashboard-target-structure.md`):

- **`api/`** — FastAPI surface. Business routers live in `api/routers/*` and are mounted by `api/router.py` under `/api`. **Paper-trading routes stay outside `/api`** (registered directly on the app), so `/paper/*` is the external contract. `app.py` is the composition root (creates the app, middleware, startup hooks, serves the frontend).
- **`domain/`** — business logic by area: `runs/` (Agent-Environment Protocol: Run/Step/Decision), `agents/`, `leaderboard/` (contest + baseline strategies registry), `backtesting/` (engine, `external_run_service`, portfolio manager), `strategies/` (free-form strategy store), `chat/`, `trading/`. Domain must not import `api/`/`app.py`.
- **`infrastructure/`** — `llm/` (the `validator` security boundary, `token_cost`, `backtest_harness`/gateway client) and `market_data/` (Alpaca bars).
- **`services/` / re-export shims** — several moved modules keep thin compatibility re-exports.
- **Persistence** (`database.py` + per-store repositories like `domain/runs/repository.py`, `domain/strategies/repository.py`): thin SQLite wrappers over `DATABASE_PATH`; schema is created lazily and self-migrates.
- **Frontend** (`dashboard/frontend/`): vanilla JS + Chart.js, no build step. Served by the backend locally/Render; also deployed static to Vercel.
- **Paths** (`dashboard/backend/paths.py`): single source of truth for on-disk locations.

### Baseline strategies (registry pattern)

`dashboard/backend/domain/leaderboard/strategies/` holds benchmark strategies (`buy_hold`, `equal_weight_index`, `market_index`, `mean_variance`, `llm_agent`, …). To add one: subclass `BaselineStrategy` (`base.py`), give it a `key`, add the class to `_STRATEGY_CLASSES` in `registry.py`. `get_strategy(config)` resolves by `strategy`/`type` key.

### LLM safety boundary

`infrastructure/llm/validator.py` is a hard security boundary: LLM trading responses must be JSON-only matching the trading schema — `tool_calls`/`function_calls` are rejected, portfolio constraints enforced, decisions logged. Do not loosen this to allow tool/web access from agent responses.

### External agents & Agent-Environment Protocol (`/api/v1`)

- **Protocol Run API** (`api/routers/runs.py` → `domain/runs/*`): an external agent authenticates with its Agent API key (`X-API-Key`) and drives a backtest step-by-step (`POST /api/v1/runs`, poll steps, submit decisions). Each step has a decision deadline (default 30s); a late decision auto-holds that step rather than failing the run.
- **External backtest engine** (`domain/backtesting/external_run_service.py`): the hour-by-hour session behind both the protocol and the legacy `/api/v1/backtest/*` routes.
- **PyPI client** (`packaging/agentictrading/`): stdlib-only Python SDK + `AgentRunner`. Published via `.github/workflows/publish-pypi.yml`.

### Agent API v2 (`/api/v2`) — the canonical agent-facing contract

Two step-driven agent surfaces coexist; they are **not peers**:

- **`/api/v2` is canonical** (`api/v2/*` routers + `execution/` backends over the same domain engines): typed Pydantic contract, per-agent scopes + token-bucket rate limits, canonical `run_id`, DB-backed idempotency (`(run_id, idem_key)`), `context_ref` provenance, self-describing `GET /api/v2/schema`. Spec/plan: `docs/superpowers/{specs,plans}/2026-06-23-agent-api-foundation-*`. New agent-facing features land here (Phase B: paper/live via `ExecutionBackend`; Phase C: MCP façade).
- **`/api/v1` is the compatibility surface** for the shipping SDK (`packaging/agentictrading`), Discord bot, and built-in agents. Keep it working; do not grow it. Migrating the SDK to v2 is the gate for publishing `agentictrading` 0.2.0.
- `execution/` sits at the backend root (not `domain/`) deliberately: the backends bind domain engines to the v2 API contract, and `test_architecture_boundaries` forbids `domain/` → `api/` imports.

## Deployment

- **Backend** → Render (`render.yaml`): `uvicorn dashboard.backend.app:app`, persistent disk at `/data`, health check `/health`.
- **Frontend** → Vercel (`vercel.json`): static `dashboard/frontend`.
- **Container** (`Dockerfile`): `WORKDIR /app`; `uvicorn dashboard.backend.app:app`.

## Gotchas

- Root `pyproject.toml` (`finagent-orchestration`) is for the **orchestration** subsystem, not the dashboard — edit `requirements.txt` for dashboard deps.
- `README.md`'s "File Structure" diagram is idealized; the real layout nests everything under `dashboard/`.
- The committed `dashboard/storage/data/backtest.db` holds seed runs referenced by `dashboard/config/defaults.json`. Importing a store module runs `CREATE TABLE IF NOT EXISTS` against `DATABASE_PATH`, so running the app locally can add empty tables to that file — don't commit those mutations. If you regenerate the DB, update `defaults.json`.
- Pytest is not in `requirements.txt`; install it separately.
- `discord.py` (for `integrations/discord_bot.py`) is an **optional** dep declared in `requirements-discord.txt` (like `requirements-sphinx.txt` for the docs build), not core `requirements.txt` — run `pip install -r requirements-discord.txt` to run the bot. It's kept out of core so web/API/backtest installs stay lean; its tests `importorskip('discord')`.
