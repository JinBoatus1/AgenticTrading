# Agent-facing API Foundation (Plan 2) — Design Spec

- **Date:** 2026-06-23
- **Owner:** Felix (FlyMiss)
- **Repo:** agent-trading-lab
- **Status:** Design — approved, ready for implementation plan
- **Programme:** Plan 2 of 3 (Plan 1 = news→sentiment signal over the feed; Plan 3 = benchmark Agentic FinSearch as an agent)
- **Charter:** `Trade Materials/ATL-Agent-API-Foundation-Plan2-Charter.html`

## 1. Goal

Turn the lab's current, implicit external-agent API into a **deliberate, documented, MCP-aligned API foundation** that any agent (Claude / GPT / Cursor / FinSearch) can target — register, fetch context (market + news + sentiment), submit decisions, get results — with versioning, auth/governance, and benchmark/leaderboard hooks.

This is **formalize-and-unify**, not rebuild. The existing surface (`POST /api/v1/agents` → `POST /api/v1/backtest/start` → poll `…/steps/current` → `POST …/decisions`) is ~80% of the contract already; the work is to give it a typed/versioned context schema (incl. Plan 1's `news_sentiment`), a documented decision/error model, scoped + rate-limited auth, backtest/paper parity, benchmark hooks, and an MCP-ready shape.

### The hard boundary (unchanged)

The **agent's LLM runs client-side.** The backend serves context and validates decisions; it never calls the agent's model. "Feeding news to an agent" means putting news in the served context envelope. `llm_validator.py` remains a hard security boundary: decision payloads are JSON-only; `tool_calls`/`function_calls` are rejected. The MCP façade (Phase C) never loosens this.

## 2. Resolved design decisions

| Fork | Decision | Rationale |
|---|---|---|
| **v1 shape / ambition** | REST is the source of truth; the surface is **MCP-shaped**; the actual MCP server is **deferred to Phase C**. | Freeze the contracts first; the later MCP server is a thin, mechanical adapter over frozen REST. |
| **Versioning** | New **`/api/v2/*`** namespace; existing `/api/v1/*` left untouched. | The agent contract becomes its own governed, documented, independently-deprecatable surface. |
| **Universe** | DJIA-30 stays the only tradable universe, but is a **declared, typed `universe` field** in the context + run config — not an implicit constant. | Matches Plan 1's DJIA-30 ∩ watchlist constraint; parameterizing later is a flip, not a rewrite (YAGNI). |
| **Mode parity** | **Backtest + paper** share one contract in v1 (same schemas, different execution backend). Live is **designed-for, not wired.** | Lets Plan 3 benchmark in backtest and run identical client code against paper. Live carries real-money/regulatory weight the programme explicitly stays behind. |
| **Transport** | **Polling**, SSE-ready. | Maps cleanly onto MCP's request/response tool model; the backtest loop is inherently lockstep. Optional SSE push is a later add for live dashboards. |
| **Auth depth** | Existing `ag_` key **+ per-agent rate-limit + basic scopes**. | Pragmatic governance without an OAuth build-out; protects the backend and enables the "do agents herd?" fairness experiment. |

## 3. The two shared contracts (couple the plans)

### 3.1 Sentiment-signal contract (from Plan 1 → graduated here into a typed field)

```jsonc
news_sentiment[SYM] = {
  "sentiment": "bullish" | "bearish" | "neutral",
  "score": -1.0..1.0,
  "headline": "…", "source": "Reuters", "url": "https://…",
  "age_hours": 3.2, "n_articles": 2
}
news_overview = "market-wide one-liner"
```

**Composition boundary:** Plan 2 *types and guarantees the slot*; Plan 1's adapter (`integrations/news_sentiment.py`) *populates it*. The `news_sentiment` key is **always present** in the context envelope (fail-closed to `{}`, `news_overview` to `null`) so agents can rely on it existing even before Plan 1 merges. Entries are validated against a typed `NewsSentimentEntry` model, scoped to `universe`, one aggregated entry per ticker.

### 3.2 Agent-API contract (Plan 2 produces → Plan 3 consumes)

Four canonical verbs, each a single REST endpoint that maps 1:1 onto a future MCP tool of the same name:

```
register        → POST   /api/v2/agents
get_context     → GET    /api/v2/runs/{run_id}/context
submit_decision → POST   /api/v2/runs/{run_id}/decisions
get_result      → GET    /api/v2/runs/{run_id}/result
```

## 4. Architecture

### 4.1 The `/api/v2` surface

| Endpoint | Verb-role | Purpose |
|---|---|---|
| `POST /api/v2/agents` | register | Create agent → `{agent_id, api_key (ag_…), session_id, scopes}` (key shown once) |
| `GET /api/v2/agents/me` | — | Resolve caller from `X-API-Key` → identity, scopes, rate-limit status |
| `POST /api/v2/agents/{id}/rotate-key` | — | Rotate key (exists today) |
| `POST /api/v2/runs` | — | Start a run. Body: `mode: backtest\|paper`, `universe: djia_30`, date-range / session params, `agent_name`, `model_name`. Returns `{run_id, mode, status, decision_timeout_seconds}` |
| `GET /api/v2/runs/{run_id}` | — | Run status: `{status, step_index, total_steps, decision_deadline_at, mode}` |
| `GET /api/v2/runs/{run_id}/context` | **get_context** | Typed context envelope for the current step |
| `POST /api/v2/runs/{run_id}/decisions` | **submit_decision** | `{idempotency_key, actions:[…]}` → ack |
| `GET /api/v2/runs/{run_id}/result` | **get_result** | `{metrics, equity, trades, decisions, manifest}` — feeds leaderboard |
| `GET /api/v2/runs/{run_id}/decisions` | — | Full decision log (audit / herding probe) |
| `POST /api/v2/runs/{run_id}/cancel` | — | Cancel a stuck run (→ `closed`) |
| `GET /api/v2/schema` | — | Self-describing: context schema, decision schema, universe, error codes, version |
| `GET /api/v2/leaderboard` | — | Ranked scored runs vs baselines (Plan 3 target) |

**Naming:** standardize on **`run`** as the canonical noun (the lab already says "run" everywhere — `agent_runs`, `/runs`). URLs become mode-neutral: `/runs/{id}/context` instead of `/backtest/{id}/steps/current`. Step-loop semantics preserved.

**MCP-shaping rule** held for every endpoint: one logical action, flat JSON in, self-contained JSON envelope out, fully described by `GET /schema`. Guarantees the Phase-C MCP façade is mechanical.

### 4.2 The parity mechanism — `ExecutionBackend`

`POST /api/v2/runs` reads `mode` and instantiates an `ExecutionBackend`:

- `BacktestBackend` — **wraps** the existing `ExternalBacktestSession` / `build_market_snapshot` (not a rewrite).
- `PaperBackend` — **wraps** `AlpacaPaperTradingClient`.
- `LiveBackend` — designed-for, documented stub, not built.

All implement one interface:

```python
class ExecutionBackend:
    def build_context(self, step) -> ContextEnvelope: ...   # identical schema both modes
    def apply_decisions(self, actions) -> ExecutionResult: ...# identical ack both modes
    def advance(self) -> None: ...
    def status(self) -> RunStatus: ...
    def result(self) -> ResultEnvelope: ...
```

Context and decision **schemas are mode-independent**; only the backend differs. This is what lets Plan 3 benchmark an agent in backtest and run identical client code against paper.

## 5. Data contracts (typed)

### 5.1 Context envelope — `GET /api/v2/runs/{run_id}/context`

Keeps today's *inner* field names (`portfolio`, `current_holdings`, `recent_trades`, `top_signals`) to make porting trivial; wraps them in a typed, versioned envelope and adds `universe` + `news_sentiment`.

```jsonc
{
  "schema_version": "2.0",
  "run_id": "…", "mode": "backtest",
  "step_index": 0, "total_steps": 48,
  "timestamp": "2026-04-15T10:30:00+00:00",
  "decision_deadline_at": "…", "decision_timeout_seconds": 30,
  "status": "waiting_decision",            // waiting_decision | loading | completed | closed
  "universe": ["AAPL","MSFT", …],          // DJIA-30, now EXPLICIT in the contract
  "portfolio":        { "cash":…, "positions_value":…, "total_equity":…, "num_positions":… },
  "current_holdings": { "AAPL": { "shares":…, "entry_price":…, "current_price":…, "position_value":…, "pnl_pct":… } },
  "recent_trades":    [ … ],
  "top_signals":      { "AAPL": { "price":…, "rsi":…, "macd":…, "macd_signal":…, "sma20":…, "sma50":…, "bb_upper":…, "bb_lower":… } },
  "news_sentiment":   { "AAPL": { "sentiment":"bullish", "score":0.62, "headline":"…", "source":"Reuters", "url":"https://…", "age_hours":3.2, "n_articles":2 } },
  "news_overview":    "market-wide one-liner or null",
  "decision_format":  { … }                // self-describing echo of how to respond
}
```

`status` values: `loading` (warming market data), `waiting_decision` (step open), `completed`, `closed`.

### 5.2 Decision contract — `POST /api/v2/runs/{run_id}/decisions`

```jsonc
{
  "idempotency_key": "uuid-v4",            // safe retries past the step_already_closed race
  "actions": [
    { "action": "buy|sell|hold", "symbol": "AAPL", "confidence": 0.0-1.0,
      "reasoning": "5-500 chars (first-class, stored, indexed for the herding probe)",
      "position_size": 0-10000, "stop_loss_price": float|null, "take_profit_price": float|null }
  ]
}
```

- **Idempotency:** server keys on `(run_id, step_index, idempotency_key)`; a replay returns the *original* ack instead of double-executing.
- **`reasoning`** becomes a first-class, stored, queryable field (already persists to `trades.reason`/`backtest_decisions`; formalized so the herding probe is a query, not a scrape).
- **Security boundary unchanged:** `tool_calls`/`function_calls` → reject (`llm_validator`).
- **Validation rules carried over** from `llm_validator`: symbol ∈ `universe`; `confidence ∈ [0,1]`; `reasoning` 5–500 chars; `position_size` 0–10000; positive-or-null stop/take prices; insufficient-cash / sell-without-position / oversized-position checks.

### 5.3 Submit ack — per-action, partial execution

Submit returns `200` with a partial-execution ack — valid actions execute, invalid ones are dropped **with reasons** (more informative than today's all-or-nothing `validation_hold`). If *all* actions are invalid, the step auto-holds (safety preserved). Sub-min-confidence actions become `hold`.

```jsonc
{
  "accepted": true,
  "executed": [ { "action":"buy", "symbol":"AAPL", "shares":10, "price":505.0 } ],
  "rejected": [ { "symbol":"ZZZ", "reason":"universe_violation" } ],
  "decision_source": "external_agent",     // external_agent | timeout_hold | validation_hold
  "next_step": 1,
  "status": "waiting_decision",            // or "completed"
  "run_id": "…", "metrics": { … }          // metrics present iff completed
}
```

### 5.4 Error model — one envelope

```jsonc
{ "error": { "code": "validation_failed|step_already_closed|run_not_found|unauthorized|forbidden_scope|rate_limited|universe_violation|insufficient_cash|invalid_symbol|invalid_status",
             "message": "human-readable", "details": { … }, "retryable": true|false } }
```

Conventional statuses: `400` validation · `401` auth · `403` scope · `404` not found · `409` step closed/conflict · `422` business-rule (e.g. insufficient cash) · `429` rate limit. `GET /api/v2/schema` publishes the full code list so clients are self-correcting.

## 6. Auth, identity & governance

- **Core (unchanged):** `ag_<token>`, SHA-256-hashed, issued once, `rotate-key` exists. Caller authenticates with `X-API-Key`; the key resolves to `agent_id` + `session_id` (agents no longer juggle `X-Session-Id` — the key carries ownership). `X-Session-Id` stays accepted for the browser dashboard.
- **Scopes** (stored on the agent record; checked per endpoint; `403 forbidden_scope` on miss):
  `agents:register` · `runs:write` · `context:read` · `decisions:write` · `runs:read`.
  Default grant on registration = all five (single-tenant research default); the *machinery* is what enables governance and future MCP auth alignment.
- **Per-agent rate limiting:** token-bucket keyed on `agent_id`, env-configurable, returns `429 + Retry-After` and `X-RateLimit-Limit/Remaining/Reset` headers. Purposes: protect the backend from a runaway agent, and enforce fairness across N agents so the herding probe is a clean experiment.

## 7. Run lifecycle

```
created → loading → waiting_decision ⇄ (submit | timeout_hold → advance) → … → completed
                                                                              ↘ failed / closed
```

`POST /api/v2/runs/{id}/cancel` → `closed`. Backtest and paper share this machine; only the `ExecutionBackend` differs. Decision timeout (`EXTERNAL_AGENT_DECISION_TIMEOUT_SECONDS`, default 30) and auto-hold-on-timeout semantics carry over from `external_backtest_service`.

## 8. Benchmark / leaderboard hooks (what Plan 3 needs)

A run emits four things:

1. **Standardized metrics** in `get_result`: `{total_return, sharpe_ratio, max_drawdown, win_rate, num_trades, final_equity, llm_calls, input_tokens, output_tokens, est_cost_usd}` — same shape across modes, comparable to existing baselines (buy-hold, DJIA index).
2. **Reproducibility manifest** per run: `{agent_name, model_name, mode, universe, date_range, decision_timeout, schema_version, news_sentiment_source}`.
3. **Per-decision context provenance:** each decision-log entry stores `decision_source`, `actions_submitted`, `actions_executed`, **and a `context_ref` (hash of the exact context — incl. `news_sentiment` — the agent saw).** Turns "N agents, identical news → measure decision correlation" into a direct query, and traces every benchmarked decision to one source of truth.
4. **Leaderboard endpoint** `GET /api/v2/leaderboard` ranks scored runs against baselines (builds on existing `leaderboard.py`/`baselines*.py`, replacing partly-mock data with real v2 runs).

## 9. File map

Honors the repo's flat-import rule: backend root has **no** `__init__.py` and modules import by bare name; new packages (`api/v2/`, `execution/`) are subpackages *with* `__init__.py`, mirroring `engines/`.

```
dashboard/backend/
├── api/v2/                          # NEW versioned package (mounted at /api/v2)
│   ├── __init__.py
│   ├── router.py                    # composes the v2 sub-routers
│   ├── models.py                    # ★ THE typed contract: ContextEnvelope, NewsSentimentEntry,
│   │                                #   DecisionRequest, ActionItem, SubmitAck, ErrorEnvelope, RunManifest, ResultEnvelope
│   ├── agents.py                    # register / me / rotate-key (+ scopes)
│   ├── runs.py                      # create · status · context · decisions · result · decisions-log · cancel
│   ├── schema.py                    # GET /api/v2/schema (self-describing)
│   └── leaderboard.py               # GET /api/v2/leaderboard (real v2 runs vs baselines)
├── execution/                       # NEW package — the parity mechanism
│   ├── __init__.py
│   ├── base.py                      # ExecutionBackend interface
│   ├── backtest_backend.py          # wraps existing ExternalBacktestSession (NOT a rewrite)
│   └── paper_backend.py             # wraps AlpacaPaperTradingClient (LiveBackend = documented stub)
├── auth_scopes.py                   # scope constants + require_scope() FastAPI dependency
├── rate_limit.py                    # per-agent token bucket
├── agent_store.py    (EXTEND: scopes column)
├── database.py       (EXTEND: idempotency table; context_ref + run_manifest; update both _init_schema & _migrate_schema)
├── llm_validator.py  (REUSE as the security boundary; DJIA_30 → the `universe` source)
└── external_backtest_service.py / paper_trading.py  (REUSE, wrapped by backends)

dashboard/examples/external_agent_client_v2.py   # NEW reference client — the v2 contract in action
docs/source/lab/agent_api.rst                     # NEW documented API surface (+ update architecture.rst)
```

`api/v2/models.py` is the centerpiece — the typed contract as Pydantic models, which also yields a clean auto-generated **OpenAPI** doc at `/openapi.json`.

## 10. Testing strategy

TDD; tests prepend the backend dir to `sys.path` per the existing pattern (`sys.path.insert(0, str(Path(__file__).parent.parent))`).

| Test file | Proves |
|---|---|
| `test_v2_contracts.py` | Models validate good payloads, reject bad (news_sentiment typing, `score ∈ [-1,1]`, decision bounds, error envelope) |
| `test_v2_runs.py` | Lifecycle create → context → decisions → result end-to-end |
| `test_v2_parity.py` | **Identical** context + decision schema validates for *both* backtest and paper backend |
| `test_v2_auth.py` | Scope miss → 403, rate-limit → 429, key resolves to agent + session |
| `test_v2_idempotency.py` | Replayed `idempotency_key` returns original ack, no double-execute |
| `test_execution_backends.py` | Both backends conform to the `ExecutionBackend` interface |

## 11. Phasing

- **Phase A — Formalize REST + typed context.** v2 namespace, `models.py` contract, `runs` over `BacktestBackend`, typed context incl. the `news_sentiment` slot, decision/idempotency/error model, `/schema`, v2 client example + docs. *Delivers the agent-API contract Plan 3 targets.*
- **Phase B — Parity + governance.** `PaperBackend` behind the same contract; scopes + rate-limits; benchmark hooks (manifest, `context_ref`, real `/leaderboard`).
- **Phase C — MCP façade (designed-for, deferred).** Thin MCP server mapping the four tools onto v2 REST; `LiveBackend`. Not built in this programme cut, but every contract above is shaped so it's mechanical.

## 12. Non-goals (the line this stays behind)

- **No alpha/strategy layer.** This is measurement apparatus, not a money-maker.
- **No live real-money execution** in v1 (designed-for only).
- **No loosening of the LLM safety boundary** — JSON-only decisions, no tool/web access from agent responses.
- **No universe expansion** beyond DJIA-30 in v1 (the field is declared so it *can* expand later).
- **No MCP server build** in v1 (REST is shaped for it; Phase C).
- Plan 2 does **not** compute sentiment — it types the slot; Plan 1 owns the computation.

## 13. Backward compatibility

`/api/v1/*` and all legacy flat routes (`/runs`, `/paper/*`, `/health`, …) are untouched. The existing `external_agent_client.py` keeps working against v1. v2 is additive; the committed seed DB and `defaults.json` are unaffected (DB changes are additive + self-migrating).
