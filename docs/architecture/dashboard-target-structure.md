# Dashboard Backend Architecture

> **Status: realized (Phase 4 complete).** The migration described by the
> planning sections below has landed. Section 0 is the authoritative, current
> backend architecture contract; the later sections are retained as historical
> design rationale.

---

## 0. Backend architecture contract (current)

### Layering

```text
API / CLI / Discord            (entrypoints: HTTP routers, scripts, discord bot)
        ↓
Domain services and logic      (dashboard/backend/domain/*)
        ↓
Infrastructure adapters        (dashboard/backend/infrastructure/*)
```

Dependencies only point downward. Domain and infrastructure modules never import
API routers or `app.py`. These rules are enforced permanently by
`dashboard/backend/tests/test_architecture_boundaries.py`.

### Canonical package map

```text
dashboard/
├── backend/
│   ├── app.py                  # composition root: middleware + include_router + frontend assets (no API route bodies)
│   ├── middleware.py           # CORS / session / CSP middleware
│   ├── database.py, paths.py, cache.py, users.py   # cross-cutting infra primitives
│   ├── baseline_generator.py   # active baseline engine helper (engine + leaderboard strategies)
│   ├── baselines_endpoint.py   # active: DB-backed baseline read for the paper router
│   ├── baseline_resolver.py    # baseline window resolution (test-covered helper)
│   ├── llm_integration_example.py  # documentation example (referenced by SECURITY.md)
│   ├── api/
│   │   ├── router.py           # aggregates routers under /api
│   │   ├── dependencies.py     # shared auth/ownership FastAPI deps
│   │   ├── auth.py, protocol_auth.py, health.py
│   │   └── routers/            # agents, agent_versions, runs, environments,
│   │                           #   external_backtest, algo, leaderboard, backtests,
│   │                           #   paper_trading, market, config, admin, health
│   ├── domain/
│   │   ├── agents/             # repository, version_repository, service
│   │   ├── backtesting/        # engine, portfolio_manager, features, metrics,
│   │   │                       #   constants, algo_service, external_run_service,
│   │   │                       #   reference_agent, baselines/paper.py
│   │   ├── chat/               # service (agent chat; import-safe, lazy client)
│   │   ├── leaderboard/        # service, baselines, strategies/*
│   │   ├── runs/               # repository, service, protocol, environment
│   │   └── trading/            # paper_session, portfolio, execution
│   └── infrastructure/
│       ├── brokers/            # alpaca_paper
│       ├── llm/                # validator, prompts, token_cost, decision_parsing, backtest_harness
│       └── market_data/        # quotes, alpaca_bars
├── scripts/                    # thin entrypoints; _bootstrap.ensure_repo_root() is the ONLY sys.path mutation
└── integrations/ (backend)     # discord_bot (import-safe, lazy token/client)
```

### Conventions

- **Run the API:** `uvicorn dashboard.backend.app:app` (canonical, used by
  `render.yaml` + `Dockerfile`). The `__main__` block in `app.py` is a real
  module entrypoint (`python -m dashboard.backend.app`) that references the app
  by its canonical import string, so the reloader resolves the same module
  identity. `getting_started.rst` documents these; `python3 dashboard/backend/app.py`
  (running the file directly) does NOT work — the top-level `dashboard.backend.*`
  imports require the repo root on `sys.path`.
- **Routes:** business routers live in `api/routers/` and are mounted by
  `api/router.py` under `/api`. **Paper-trading routes stay outside `/api`** and
  are registered directly on the app, so `/paper/*` (not `/api/paper/*`) is the
  external contract.
- **New router?** add it under `api/routers/` and register it in
  `api/router.py` (or directly on the app only if it must avoid the `/api`
  prefix, like `paper_trading`).
- **New domain logic?** put it under `domain/<area>/`; it must not import API or
  `app.py`.
- **Adapters:** market-data → `infrastructure/market_data/`, broker →
  `infrastructure/brokers/`, LLM → `infrastructure/llm/`.
- **Scripts** are thin entrypoints. They import the backend via
  `dashboard.backend.*` after calling `_bootstrap.ensure_repo_root()`; backend
  code never imports `dashboard.scripts`.
- **Imports:** first-party imports use the canonical `dashboard.backend.*` path.
- **Backend tests:** `python -m pytest dashboard/backend/tests -q` (use
  `.venv/bin/python` so optional deps like `discord.py` are present).

```python
# canonical import examples
from dashboard.backend.domain.agents.repository import AgentStore, agent_store
from dashboard.backend.infrastructure.llm.validator import validate_llm_response
from dashboard.backend.infrastructure.market_data.quotes import get_market_quotes
from dashboard.backend.api.routers.leaderboard import router as leaderboard_router
```

### Compatibility shims removed

All backward-compatibility re-export shims from the migration have been deleted
(Phase 4A): the flat root modules (`agent_store`, `agent_version_store`,
`algo_prompt`, `algo_service`, `environments`, `external_backtest_service`,
`llm_validator`, `market_data`, `paper_baselines`, `paper_trading`, `protocol`,
`run_service`, `run_store`, `token_cost`), the `api/<name>.py` router shims, and
the `engines/` and `services/` packages. The dead/duplicate baseline modules
`baselines.py` and `baseline_data.py` were also removed (Phase 4B). Import the
canonical `dashboard.backend.*` paths instead.

### Intentionally retained (not removed)

- `app.py` `__main__` launcher — direct execution is documented.
- `baseline_generator.py`, `baselines_endpoint.py` — active runtime consumers.
- `baseline_resolver.py` — test-covered helper (no runtime consumer yet).
- `llm_integration_example.py` — referenced by `SECURITY.md` as an example.
- This document does **not** claim every legacy-looking module was removed; the
  above are deliberate, consumer-backed retentions.

---

## 1. Proposed final directory tree

```text
dashboard/
├── backend/
│   ├── __init__.py
│   ├── app.py                         # app factory + ASGI app only (no inline business routes)
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── router.py                  # aggregates routers under /api
│   │   ├── dependencies.py            # shared FastAPI deps (auth/session); absorbs protocol_auth + _extract_bearer_token
│   │   └── routers/
│   │       ├── health.py
│   │       ├── auth.py
│   │       ├── agents.py
│   │       ├── agent_versions.py
│   │       ├── runs.py
│   │       ├── backtests.py           # merges external_backtest + legacy /backtest routes from app.py
│   │       ├── paper_trading.py       # paper account/positions/trades/baselines (lifted from app.py)
│   │       ├── algo.py
│   │       ├── leaderboard.py
│   │       └── environments.py
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py                  # settings (PORT, DB path, timeouts) via pydantic-settings
│   │   ├── paths.py
│   │   ├── middleware.py
│   │   ├── logging.py                 # (new) replace scattered print() debug
│   │   └── exceptions.py              # (new) shared error types / handlers
│   │
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── agents/                    # models.py · service.py · repository.py · version_repository.py
│   │   ├── auth/                      # models.py · service.py · repository.py   (was users.py)
│   │   ├── runs/                      # models.py · service.py · repository.py · protocol.py · environment.py
│   │   ├── backtesting/
│   │   │   ├── engine.py              # time loop (from HourlyBacktester)
│   │   │   ├── features.py            # TechnicalIndicators
│   │   │   ├── observation.py         # portfolio_state -> observation
│   │   │   ├── reference_agent.py     # rule-based decision
│   │   │   ├── metrics.py             # sharpe / max_dd
│   │   │   ├── serialization.py       # result-dict assembly
│   │   │   ├── external_run_service.py# external-agent loop (was external_backtest_service)
│   │   │   ├── algo_service.py        # custom-algo orchestration
│   │   │   └── baselines/             # generator.py · paper.py · queries.py · leaderboard.py
│   │   ├── trading/
│   │   │   ├── portfolio.py           # portfolio state/valuation (from PortfolioManager)
│   │   │   ├── execution.py           # execute_actions
│   │   │   ├── orders.py              # order models / orders<->actions (from protocol helpers)
│   │   │   └── risk.py                # risk validation (reuses llm_validator constraints)
│   │   └── leaderboard/               # models.py · service.py · strategies/ (was engines/strategies)
│   │
│   ├── infrastructure/
│   │   ├── __init__.py
│   │   ├── database.py
│   │   ├── cache.py
│   │   ├── market_data/
│   │   │   ├── alpaca.py              # live quotes (was market_data.py)
│   │   │   ├── alpaca_bars.py         # historical bars (from AlpacaDataLoader)
│   │   │   └── yahoo.py               # (was strategies/_yahoo.py)
│   │   ├── brokers/
│   │   │   └── alpaca_paper.py        # (was paper_trading.py)
│   │   └── llm/
│   │       ├── validator.py           # (was llm_validator.py validation core)
│   │       ├── prompts.py             # (was algo_prompt.py + prompt builders)
│   │       ├── token_cost.py
│   │       ├── backtest_harness.py    # make_trading_decision_with_llm + Anthropic wiring
│   │       └── decision_parsing.py    # fix_json_formatting + parsing
│   │
│   ├── integrations/
│   │   ├── __init__.py
│   │   └── discord_bot.py             # imports backend.domain.chat... (normalized)
│   │
│   └── tests/                         # mirrors domain/infra/api; isolated-DB fixtures
│
├── scripts/
│   ├── backtest/
│   │   ├── run_hourly_agent.py        # thin CLI -> backend.domain.backtesting
│   │   ├── run_custom_algo.py         # thin CLI (subprocess target)
│   │   └── legacy_backtest.py         # (archived backtest.py + backtest_engine.py) if retained
│   ├── operations/
│   │   └── deploy_leaderboard_model.py
│   └── diagnostics/
│       ├── check_alpaca_subscription.py
│       └── diagnose_alpaca_data.py
│
├── examples/
│   ├── http/                          # external_agent_client, protocol_policy_demo
│   └── sdk/                           # sdk_* (use agentictrading)
│
├── frontend/                          # unchanged
├── config/                            # defaults.json, leaderboard.json (+ optimization_config if kept)
└── storage/                           # backtest.db, cache/, backups/, artifacts (unchanged)
```

---

## 2. Responsibility statement per directory

| Directory | Responsibility | May depend on |
|---|---|---|
| `backend/app.py` | Compose the FastAPI app (middleware, routers, lifespan). No business logic, no inline routes. | `api/`, `core/` |
| `backend/api/` | HTTP transport: request/response models, routing, auth dependencies. Thin; delegates to `domain`. | `domain/`, `core/` |
| `backend/core/` | Cross-cutting concerns: config, paths, middleware, logging, exceptions. No domain knowledge. | (stdlib/third-party only) |
| `backend/domain/` | Business logic: agents, auth, runs/protocol, backtesting, trading, leaderboard. Framework-agnostic. | `domain/`, `infrastructure/` (via interfaces), `core/` |
| `backend/infrastructure/` | Adapters to the outside world: DB, cache, market data, brokers, LLM. No FastAPI, no domain rules. | `core/` |
| `backend/integrations/` | Out-of-band entrypoints (Discord). Compose domain like a mini-app. | `domain/`, `core/` |
| `backend/tests/` | Tests mirroring the above; isolated DB. | everything |
| `scripts/` | **Thin** CLI wrappers only. Parse args, call `backend.domain`/services, print/serialize. | `backend.*` |
| `examples/` | Out-of-process demos (HTTP or SDK). Never import backend code. | `agentictrading` SDK / stdlib HTTP |
| `frontend/` | Static UI. | (served over HTTP) |
| `config/` | Declarative JSON config consumed by backend. | — |
| `storage/` | Runtime data + artifacts. | — |

---

## 3. Allowed dependency directions

```text
entrypoints (app.py, scripts/, integrations/, examples-over-HTTP)
      ↓
api/  (transport)            scripts/ (CLI)        integrations/ (bot)
      ↓                          ↓                       ↓
            ───────────►  domain/  ◄───────────
                            ↓
                     infrastructure/   (adapters)
                            ↓
                         core/  (config/paths/logging)
```

Concretely allowed:
- `api → domain → infrastructure → core`
- `scripts → domain` (and `→ infrastructure`/`core` if needed)
- `integrations → domain`
- `domain → infrastructure` **only through narrow interfaces/adapters**
- anything → `core`

## 4. Forbidden dependency directions

- `domain → api` (no FastAPI types in domain). **Forbidden.**
- `infrastructure → api` and `infrastructure → domain`. **Forbidden.**
- `backend → scripts` (the current violation). **Forbidden.**
- `core → domain` / `core → infrastructure`. **Forbidden.**
- `examples → backend` (must stay HTTP/SDK). **Forbidden.**
- domain modules importing **deployment-specific paths** directly (use `core/config` + `core/paths`). **Forbidden** (fixes the `algo_service` `DATA_DIR` issue).
- import-time side effects that require secrets (e.g. `require_env` at module top). **Forbidden** — move to explicit init/DI.

---

## 5. Naming conventions

- Packages/modules: `snake_case`; no `-`.
- One concept per module; avoid suffix-only differentiation across folders (no `service.py` in 5 places at root).
- Within a domain area use consistent role filenames: `models.py`, `service.py`, `repository.py`.
- Repositories end in `repository.py` (replaces the `*_store.py` convention).
- Infrastructure adapters named by technology: `market_data/alpaca.py`, `brokers/alpaca_paper.py`, `llm/validator.py`.
- Routers named by resource (plural): `routers/agents.py`, `routers/runs.py`.
- CLIs are verbs: `scripts/backtest/run_hourly_agent.py`.
- No module named `*_endpoint.py` for non-routers (rename `baselines_endpoint.py` → `baselines/queries.py`).

---

## 6. Rules for deciding where new code belongs

Ask, in order:
1. **Is it HTTP shape (request/response/route/auth)?** → `api/` (delegates to domain).
2. **Is it a business rule / workflow / entity?** → `domain/<area>/` (`service.py` for workflow, `models.py` for entities, `repository.py` for persistence).
3. **Does it talk to an external system (DB, broker, market data, LLM, cache)?** → `infrastructure/<kind>/`.
4. **Is it config/paths/logging/error plumbing?** → `core/`.
5. **Is it a command a human runs?** → `scripts/<group>/` as a thin wrapper.
6. **Is it a demo for external users?** → `examples/` (HTTP/SDK only).
7. If it seems to belong in two places, split it: keep the rule in `domain`, the IO in `infrastructure`, the shape in `api`.

---

## 7. How the layers interact

- **API routers** depend on **domain services** and on `api/dependencies.py` (auth/session). They never touch the DB directly; they translate domain results into response models.
- **Domain services** orchestrate **repositories** (persistence) and **infrastructure adapters** (market data, broker, LLM). They contain the rules (validation, run lifecycle, metrics) and are import-safe (no secrets at import).
- **Repositories** wrap `infrastructure/database.py`; they are the only place that knows SQL/schema.
- **Infrastructure adapters** expose plain functions/classes; they accept config from `core/config` rather than reading env/paths ad hoc.
- **Scripts** import `backend.domain.*` services and call them; they own argparse + serialization only. The previous "library inside a script" pattern is eliminated.
- **Examples** call the running service over HTTP (raw or via the `agentictrading` SDK).

---

## 8. Relationship to the Python SDK (`packaging/agentictrading/`)

- The SDK is a **standalone PyPI package** with a `src/` layout, its own `pyproject.toml`, tests, and CI (`.github/workflows/publish-pypi.yml`). It is a **pure HTTP client** of the backend's REST API (uses `urllib`/`httpx`-style calls), and **does not import any backend implementation code**. This is the correct boundary and must be preserved.
- Direction of knowledge: **SDK → REST API (over the wire)**, never `SDK → backend` as a Python import, and never `backend → SDK`.
- The **shared contract** is the Agent-Environment Protocol (`docs/api/agent-environment-protocol-v1.md`) and the response models. To keep them in sync without code coupling:
  - Treat the protocol doc + an OpenAPI schema (FastAPI already generates one) as the source of truth.
  - The SDK's `models.py` mirrors the protocol; the backend's `domain/runs/protocol.py` + `api` response models implement it. Changes flow through the protocol/OpenAPI, not through imports.
- `examples/sdk_*.py` exercise the SDK against a running backend; they belong in `examples/sdk/` and remain import-decoupled from `backend/`.

---

## Practical placement examples

| New thing | Goes in | Why |
|---|---|---|
| A new backtest **baseline** (e.g. NASDAQ index) | `backend/domain/backtesting/baselines/<name>.py` (+ register in strategies registry if leaderboard-visible) | Business calculation; baselines are a domain concern. |
| A new **Alpaca endpoint adapter** (e.g. options chain) | `backend/infrastructure/market_data/alpaca.py` (or a new adapter module under `market_data/`) | External IO = infrastructure. |
| A new **Agent API route** | `backend/api/routers/agents.py`, delegating to `backend/domain/agents/service.py` | Transport in `api`, logic in `domain`. |
| A new **risk validator** | `backend/domain/trading/risk.py` | Pure business rule; reused by backtesting + protocol. |
| A **one-off diagnostic** command | `backend/scripts/diagnostics/<name>.py` (thin) calling domain/infra | Human-run command; keep logic in backend. |
| A **reusable trading calculation** (e.g. position sizing) | `backend/domain/trading/` (e.g. `portfolio.py`/`orders.py`) | Domain math, framework-agnostic, unit-testable. |

---

## Deviations from the reference layout (with rationale)

1. **No top-level `services/` or `stores/` dumping grounds.** Per the task's guidance, application services and repositories live *inside their domain area* (`domain/runs/service.py`, `domain/agents/repository.py`). The current `services/` package is dissolved into domains.
2. **Avoided overlapping `trading/ + engines/ + market/ + baselines/` at top level.** `engines/strategies` becomes `domain/leaderboard/strategies`; baselines become `domain/backtesting/baselines`; market data becomes `infrastructure/market_data`. Responsibilities are distinct: *backtesting* = run/loop/metrics; *trading* = portfolio/execution/orders/risk primitives; *leaderboard* = ranking + strategy registry.
3. **`backtest_hourly_agent.py` is decomposed, not relocated** (see manifest §Special analysis). Its market IO → `infrastructure`, its rules → `domain`, its CLI → `scripts/backtest/`.
4. **Added `core/logging.py` and `core/exceptions.py`** (not in current code) to replace ad-hoc `print()` debugging in `app.py`/services and to centralize error envelopes (`protocol.ProtocolError` mapping).
5. **`paper_trading` routes lifted out of `app.py`** into `api/routers/paper_trading.py`; `app.py` becomes a thin factory. The current `app.py` holds ~900 lines of inline routes — keeping them there would undermine the layering.
6. **`baselines_endpoint.py` renamed** to `baselines/queries.py` (it is a query helper, not an HTTP endpoint).
7. **`examples/` split into `http/` and `sdk/`** to make the (preserved) decoupling explicit.
