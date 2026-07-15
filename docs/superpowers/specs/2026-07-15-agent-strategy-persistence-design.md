# Durable agent & strategy storage (`DATABASE_URL` Postgres backends)

**Date:** 2026-07-15
**Status:** Approved design, pre-implementation
**Precedent:** `docs/superpowers/plans/2026-07-08-user-account-persistence-fix.md` (the `USERS_DATABASE_URL` users fix — this design extends that exact pattern to agents and strategies)

## Problem

Prod runs on Render's free tier with no persistent disk, so the SQLite database at
`DATABASE_PATH` resets to the committed seed `backtest.db` on every deploy (and merging
to `main` auto-deploys). User accounts were rescued from this in 2026-07 via an optional
Postgres backend (`USERS_DATABASE_URL`, Neon in prod), but everything users create
*besides* accounts still evaporates:

- **Agents** (`external_agents`, created by `AgentStore._init_schema()`,
  `dashboard/backend/domain/agents/repository.py:87-155`): agents vanish from
  "My Agents", and — worse — **issued API keys stop validating**, because
  `resolve_api_key()` (`repository.py:340-358`) is the sole auth path for both
  `/api/v1` and `/api/v2`. Every SDK integration and Discord-bot agent breaks on
  every deploy.
- **Agent versions** (`agent_versions`,
  `dashboard/backend/domain/agents/version_repository.py:83-111`): immutable
  reproducibility snapshots, lost with their agents.
- **Strategies** (`strategies`,
  `dashboard/backend/domain/strategies/repository.py:63-80`): 8-char share codes die.

A structural wrinkle: prod already has a split-brain ownership model. The `users` half
of the user→agent relationship lives in durable Neon Postgres while the `agents` half
lives in wipe-on-deploy SQLite, joined by `external_agents.owner_user_id` — which is
*declared* as `REFERENCES users(id)` but never enforced (no `PRAGMA foreign_keys`
anywhere in the backend). Moving agents into the same Postgres database as users is the
only option that makes that relationship joinable again.

## Decisions (settled with Felix, 2026-07-15)

1. **Scope:** `external_agents` + `agent_versions` + `strategies` move to optional
   Postgres. Run history (`agent_runs`, `equity_timeseries`, `trades`,
   `protocol_runs`, `protocol_steps`, `idempotency_keys`, `run_manifest`) stays in
   ephemeral SQLite — explicitly a later phase (write-heavy per-step engine writes;
   Neon free tier is ~0.5 GB).
2. **Config:** one new env var **`DATABASE_URL`** consumed by the three new store
   factories. The users factory gains a fallback (`USERS_DATABASE_URL or
   DATABASE_URL`) so future deployments need only one var; prod already sets
   `USERS_DATABASE_URL`, so users-store behavior does not change.
3. **Approach:** literal copy of the proven `users.py` dual-backend pattern —
   hand-written Postgres twin class per store with an identical public method
   surface, per-store factory, no base class, no SQL-translation layer, no ORM.
   (Rejected: a home-grown dual-dialect adapter — upsert/error semantics differ
   subtly between dialects and the translation layer is where silent bugs live; and
   SQLAlchemy — a heavyweight new dependency this thin-stdlib-wrapper codebase
   doesn't need at this scale.)

## Architecture

### Backend selection

Each store module gets a factory cloned from `_build_user_store()`
(`dashboard/backend/users.py:312-321`):

```python
def _build_agent_store():
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        from dashboard.backend.domain.agents.repository_postgres import PostgresAgentStore
        return PostgresAgentStore(database_url)
    return AgentStore()

agent_store = _build_agent_store()
```

Module-level singleton names (`agent_store` at `repository.py:551`,
`agent_version_store` at `version_repository.py:198`, `strategy_store` at
`domain/strategies/repository.py:156`) are unchanged, so no caller changes anywhere.
Verified: no **production** code outside these three modules runs raw SQL against
these tables — all 16+ agent endpoints and the strategy routes go through the
singletons. Two *test* files are known exceptions
(`tests/test_v2_http_runs.py:49-52`, `tests/test_v2_auth.py:57-61`: they reach into
`agent_store._get_connection()` and run raw `UPDATE external_agents ... ?` SQL to set
scopes). They always run under SQLite (conftest strips the env vars), so they stay
valid unchanged — but the new `@pg_only` tests must not copy that fixture pattern;
use public store methods or dialect-appropriate SQL.

`_build_user_store()` changes to:

```python
database_url = os.getenv("USERS_DATABASE_URL") or os.getenv("DATABASE_URL")
```

### New modules

| Module | Class | Twin of |
|---|---|---|
| `domain/agents/repository_postgres.py` | `PostgresAgentStore` | `AgentStore` |
| `domain/agents/version_repository_postgres.py` | `PostgresAgentVersionStore` | `AgentVersionStore` |
| `domain/strategies/repository_postgres.py` | `PostgresStrategyStore` | `StrategyStore` |

Each twin defines its own `_get_connection()` inline —
`psycopg.connect(self.database_url, row_factory=dict_row)` — exactly like
`users_postgres.py:30-31`. (A shared `pg.py` connection module was considered and
rejected: it would deviate from the precedent's shape, and the `@pg_only` test
fixtures mirror `test_users_postgres.py:56-65`, which call `store._get_connection()`
as an instance method. Consolidation across the four twins is possible later.)

Shared pure helpers are imported from each twin's SQLite module where they exist as
module-level functions — `_utcnow_iso`, `_hash_api_key`, `_new_api_key` from
`domain/agents/repository.py:29-38` — same convention as `users_postgres.py:18`
importing from `users.py`. Note the limits of this: `_utcnow_iso` is independently
defined per SQLite module (import each twin's own), and the strategies module has
**no** separable code-generation helper — the share-code retry logic is fully inlined
in `StrategyStore.create()`, so `PostgresStrategyStore.create()` reimplements that
whole method (see the dialect section for the required restructuring). Driver:
`psycopg[binary]==3.3.4`, already in `requirements.txt:49`. Connections are per-call
(no client pooling); prod **must** use Neon's pooled (`-pooler`) connection string —
with per-call connects across four stores (these three plus users), the direct
non-pooled Neon endpoint's connection cap is a real risk under concurrent agent
polling.

### Method surfaces to port (the contract, enumerated)

| Store | Public methods |
|---|---|
| `AgentStore` (`repository.py:74-548`) | `create_agent`, `register_or_get_agent`, `list_agents`, `list_builtin_agents`, `get_agent`, `get_agent_by_session`, `resolve_api_key`, `claim_browser_agents_to_user`, `claim_agent`, `reclaim_agent`, `rotate_api_key`, `update_agent`, `delete_agent`, `owns_agent` |
| `AgentVersionStore` (`version_repository.py:70-198`) | `create_version`, `get_version`, `list_versions` |
| `StrategyStore` (`domain/strategies/repository.py:50-156`) | `create`, `get`, `set_last_run` |

None use `executemany`, json1 functions, `LIKE`, or `rowid`/`lastrowid`. `update_agent`
(`repository.py:455`) builds dynamic SQL from kwargs using the `_UNSET` sentinel
(`repository.py:26`) to distinguish omitted from explicit-`None` — dialect-neutral
apart from placeholder style, but port it carefully.

### Failure semantics — fail loud, and fail visible

If `DATABASE_URL` is set but Postgres is unreachable, the twin's `__init__` (which
connects to run `_init_schema()`) raises and **the app refuses to start**. To be
precise about the mechanism: the singletons are bare module-level assignments reached
transitively when `app.py` imports the router chain, so this is a **raw import-time
exception** (not a FastAPI startup-hook failure), propagating from whichever store
module the import graph reaches first. Accepted as-is — it exactly matches the
`PostgresUserStore` precedent's behavior. No silent fallback to SQLite — that would
recreate the account-loss failure mode this pattern was built to kill (see CLAUDE.md,
"Fail-closed is not fail-visible").

The dangerous case is the *other* branch: `DATABASE_URL` simply **unset** silently
selects ephemeral SQLite, and nothing in the app today logs which backend won (true
even for the shipped users store). Each new factory therefore emits one startup log
line — e.g. `agent_store backend: postgres` / `agent_store backend: sqlite (ephemeral
on Render)` — so a misconfigured deploy is visible in logs instead of byte-identical
to a healthy one.

## Postgres schema

Dialect conventions follow `users_postgres.py`: `TEXT` ISO-8601 timestamps (the SQLite
stores already write `_utcnow_iso()` strings, so ordering/comparison parity is exact),
JSON kept as `TEXT` (not JSONB), `DOUBLE PRECISION` for `cash_allocation`, idempotent
`CREATE TABLE IF NOT EXISTS` plus lazy `ALTER TABLE ADD COLUMN IF NOT EXISTS`
migrations in `_init_schema()`. All unique constraints and indexes carry over:
`api_key_hash` UNIQUE, `session_id` UNIQUE, indexes on `owner_user_id`,
`owner_browser_session`, `agent_type`, `agent_versions(agent_id, created_at)`.

**Deliberate deviation — no FK constraint on `owner_user_id`.** It stays a plain
`INTEGER`. Rationale: SQLite never enforced it (no `PRAGMA foreign_keys` anywhere in
the backend), the app already owns this integrity (`owns_agent`,
`claim_browser_agents_to_user`), and declaring it fails in both configurations: in
the same-database config it makes agent-store init order-dependent on the users table
already existing; in the split config (`USERS_DATABASE_URL` and `DATABASE_URL`
pointing at different databases) it is categorically impossible — Postgres does not
support cross-database foreign keys at all. In the recommended prod config (same Neon
DB) real joins become possible; enforcement stays app-level, as today. (For scope
clarity: `agent_versions` declares no FK to `external_agents` in SQLite either —
`version_repository.py:87-101` — so no equivalent question arises there.)

### Dialect-sensitive idioms (verified against the three modules)

- `?` placeholders → `%s` (everywhere).
- `PRAGMA table_info` column probing (AgentStore's lazy migrations) →
  `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`.
- **`INSERT OR IGNORE` / `INSERT OR REPLACE` do not appear in any of the three
  in-scope modules** — every insert is a plain `INSERT`. (Both idioms exist only in
  `database.py`'s out-of-scope run tables.) Do not spend implementation time hunting
  for them.
- **The strategy share-code retry loop must be restructured, not translated.**
  `StrategyStore.create()` (`domain/strategies/repository.py:95-128`) opens one
  connection and catches `sqlite3.IntegrityError` per attempt, retrying on the same
  connection — up to 20 times, then widening the code space. That structure is
  invalid in Postgres: the first `UniqueViolation` aborts the transaction, and every
  subsequent statement on that connection raises
  `psycopg.errors.InFailedSqlTransaction` — a literal port 500s on the first real
  collision. **Required approach:** per attempt, run
  `INSERT INTO strategies (...) VALUES (...) ON CONFLICT (code) DO NOTHING` and treat
  `cursor.rowcount == 0` as the collision signal (no exception handling in the retry
  path at all). Preserve the retry count and code-space-widening behavior exactly.

## Performance trade-offs (accepted, with eyes open)

- `resolve_api_key()` runs on every agent-authenticated request and performs a read
  plus a `last_used_at` UPDATE — two Neon round-trips per request.
  `register_or_get_agent()` (`repository.py:211-252`) is worse: up to three
  sequential connect/query/close cycles per call. Accepted because the users store
  already does per-request Postgres session lookups, and the pooled URL amortizes
  connection setup. If latency ever matters, the existing TTL cache
  (`dashboard/backend/cache.py`) can front the hash→agent lookup. Future work, not
  built now.
- **Neon free-tier cold starts:** compute suspends after idle minutes and takes
  multi-second wakes. Protocol runs have a 30s per-step decision deadline; a cold
  start stacked on LLM latency eats into that budget after quiet periods. Accepted
  for now (a late decision auto-holds the step rather than failing the run); if it
  bites, a keep-alive ping is the escape hatch.

## Migration, seeding & rollout

- **No data migration:** prod agent/strategy data evaporates by definition; first
  Postgres startup auto-creates empty schema.
- **Built-in agents:** they are ordinary `external_agents` rows with
  `agent_type='builtin'` created via the normal API (the two in the seed DB are just
  data). Post-cutover they are recreated once through the API and persist thereafter.
  No code-level seeding.
- **Rollout — env var FIRST, then merge.** Merging to `main` auto-deploys prod, and
  an *unset* `DATABASE_URL` silently selects ephemeral SQLite (only set-but-unreachable
  fails loud) — so merging first would open an invisible window where the feature
  doesn't work. Order: (1) set `DATABASE_URL` in the **Render dashboard** (same Neon
  database as `USERS_DATABASE_URL` — which itself lives only in the dashboard, not in
  `render.yaml`; the yaml is known-drifted from prod and editing it alone does
  nothing) → (2) merge; CI auto-deploys on green main → (3) confirm the new
  `agent_store backend: postgres` startup log line → (4) **live verification:**
  create an agent, trigger a redeploy, confirm the agent still lists and its API key
  still resolves. Optionally add `DATABASE_URL` to `render.yaml` with `sync: false`
  as documentation, clearly not as the mechanism.

## Testing (mirrors the users fix's three tiers)

1. **Whole suite stays on SQLite:** `dashboard/backend/tests/conftest.py` must strip
   `DATABASE_URL` at import time, alongside the existing `USERS_DATABASE_URL` strip
   (`conftest.py:44-47`). Without this, a dev with prod env vars set would run the
   test suite against the production Neon database.
2. **Dispatch tests** per factory: `DATABASE_URL` set → Postgres twin selected;
   unset → SQLite; users factory precedence (`USERS_DATABASE_URL` wins over
   `DATABASE_URL`). No live Postgres needed (mirror
   `test_users_postgres.py:29-53`).
3. **`@pg_only` behavioral tests** per store, gated on `TEST_POSTGRES_URL` (mirror
   `test_users_postgres.py:76-124`): agent create/claim/rotate/resolve lifecycle
   including browser-session→user claim; `update_agent` partial updates (`_UNSET`
   sentinel); version immutability; `last_used_at` update on resolve; and the
   strategy share-code collision path — which must **force a real collision**
   (monkeypatch `secrets.token_hex` to return a duplicate before a fresh value), not
   mock the insert. No existing SQLite test exercises a forced collision
   (`test_strategy_store.py` only checks 25 random codes don't collide by chance), so
   this test is new for both backends and should run against SQLite too.

## Config & docs surface

- `.env.example`: document `DATABASE_URL` next to `USERS_DATABASE_URL` (`:76-83`),
  explicitly contrasting with `DATABASE_PATH` (local SQLite file for everything vs
  durable Postgres for user-created content).
- `render.yaml`: optionally add `DATABASE_URL` with `sync: false` as documentation —
  the real mechanism is the Render dashboard (see Rollout).
- CLAUDE.md: extend the env/credentials section and the user-account-persistence
  gotcha to cover agents/strategies.

## User-facing docs made true by this change (follow-ups, not edited mid-session)

These currently promise durability the platform doesn't deliver; once this ships they
become accurate and should be revisited:

- `docs/source/lab/external_agents.rst:50-53` (persistent `session_id`), `:73`
  (resolve api_key "at any time"), `:310` (leaderboard ranking of registered agents)
- `docs/api/python-sdk-quickstart.md:161-182` ("create agent once, reuse across runs";
  `create_agent_version`)
- `packaging/agentictrading/README.md:66` (register on dashboard to get an API key)
- `docs/architecture/discord-to-backtest.md:9` (create a built-in agent first)
- `README.md:50-61` (customizable agents, leaderboard competition)

## Out of scope

- Run-history / leaderboard durability (phase 2 candidate; revisit Neon storage
  budget and per-step write chattiness then)
- Caching `resolve_api_key()` lookups
- ORM / migration-framework adoption
- Render paid tier / persistent disk changes
