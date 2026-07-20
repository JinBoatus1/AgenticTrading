# Durable run history (`RUNS_DATABASE_URL` Postgres backend)

**Date:** 2026-07-20
**Issue:** #140 (Agent run history still evaporates on every deploy)
**Status:** Approved design — phase 1 of the run-history migration (the "cold half")
**Predecessor:** `2026-07-15-agent-strategy-persistence-design.md` (Decision 1 there deferred
run history to "a later phase"; this spec is that phase's first slice)

## Problem

Prod runs on Render's free tier with no persistent disk, so `DATABASE_PATH` resets to the
git-committed seed `backtest.db` on every deploy — and merging to `main` auto-deploys. Since
PR #134, agents/versions/strategies survive deploys (`CONTENT_DATABASE_URL`) and accounts
survive (`USERS_DATABASE_URL`), but every backtest run, equity curve, trade log, and decision
log still dies with the deploy. Concretely:

- The daily leaderboard's LLM entries (`agent_runs` rows) evaporate, which is why issue #145
  (the unscheduled refresh job) is blocked: an off-instance cron would write to a database
  prod never reads.
- A registered agent survives a deploy while its entire run history does not.
- Run-detail pages (equity, trades, decision logs) silently lose everything created since the
  last deploy.

Issue #140's standing decision (2026-07-18) was "accept + document the split"; the fleet
wiring plan (2026-07-20) promoted resolving it to the literal first step (P0.1/D1) because it
gates #145 and the paper-trading track. This spec executes that promotion.

## Decisions (settled with Felix, 2026-07-20)

1. **Scope: the cold half only.** Five tables move to Postgres — `agent_runs`,
   `equity_timeseries`, `trades`, `backtest_decisions`, `run_manifest`. All are written at
   run finalize (batched) or once per run. The hot per-step tables — `idempotency_keys`,
   `protocol_runs`, `protocol_steps` — **stay in SQLite**: they are written 1–2× per step
   synchronously inside the agent's HTTP request, where a Neon round-trip (and free-tier
   cold-start, multi-second wake) would sit inside the 30s decision deadline. Per-step
   operational state is ephemeral today and remains ephemeral; that is unchanged behavior,
   not a regression. Moving it durably is a follow-up with its own latency design.

2. **Topology: a dedicated Neon project** (`ATL-runs-main`, provisioned 2026-07-20, Postgres
   18.4 — matching CI's `postgres:18` pin from issue #138). This is the formal D1 sign-off.
   Rationale: its own free-tier storage/compute allotment isolates the largest, hottest
   tables' growth from the auth-critical users/content database, and the consumer sweep found
   **no code path that JOINs run tables with content/users tables** — every cross-reference is
   already a two-query Python join (and already cross-database in prod since #134), so
   same-database JOIN capability buys nothing today. Connection string lives only in Render's
   env config (and CI secrets if ever needed) — never in the repo.

3. **Env var: `RUNS_DATABASE_URL`.** Scoped name per the established convention (states what
   it backs; never `DATABASE_URL`, which ambient Heroku-convention values could poison). No
   fallback chain to/from `CONTENT_DATABASE_URL` or `USERS_DATABASE_URL` — unset means
   ephemeral SQLite, and the startup line makes the choice visible.

4. **R2/object-storage offload: deferred, seam reserved.** The only sizable blob in scope is
   `backtest_decisions.actions_submitted` (~880 KB per 252-step protocol run; zero such rows
   exist in prod today). The dedicated 0.5 GB Neon project holds hundreds of blob-inline runs;
   daily leaderboard runs add only ~25 KB each (equity points, no decisions). We add a
   nullable `actions_trace_ref TEXT` column **at ship time** — reserving the offload seam
   while it is free, instead of walking into the forgotten-`ALTER` → `UndefinedColumn` trap
   later. No R2 client, credentials, or read-path indirection in this change.

5. **Non-goals, explicit.** (a) Multi-worker execution safety: the per-agent active-run cap
   and idempotent-replay guarantees are enforced by in-process `threading.Lock`s, and the DB
   rows are replay caches — moving tables to Postgres makes *history* durable but does not
   make horizontal scaling of live runs safe. Single-worker assumption stands (v2 spec §12).
   (b) Fixing adjacent pre-existing defects found during the design sweep (broken
   `/paper/start-session` insert, `list_agents_with_stats` N+1, `metadata` population
   inconsistency) — filed as follow-up issues instead, so this PR stays one concern.

## Architecture

### Backend selection

`database.py` keeps `BacktestDatabase` (SQLite) untouched as the default. A factory cloned
from `users.py::_build_user_store()` replaces the bare singleton assignment:

```python
def _build_backtest_db():
    database_url = os.getenv("RUNS_DATABASE_URL")   # RUNS_DATABASE_URL only, deliberately.
    if database_url:
        from dashboard.backend.database_postgres import PostgresBacktestDatabase
        print(f"run history backend: postgres ({describe_database_url(database_url)})")
        return PostgresBacktestDatabase(database_url)
    print("run history backend: sqlite (ephemeral on Render)")
    return BacktestDatabase()

db = _build_backtest_db()
```

`print()`, not `logger.info()` — backend loggers emit nothing under the deployed uvicorn
config. Fail-loud: `PostgresBacktestDatabase.__init__` validates via `require_postgres_url()`
(never echoes the input), runs DDL eagerly, and an unreachable Postgres fails app startup
rather than silently falling back to SQLite. Both shared helpers come from `db_url.py`.

### The delegation twin (why not split the class)

Thirteen backend modules import the `db` singleton; `BacktestDatabase`'s public surface mixes
cold-half methods with two hot-half methods (`get_idempotency`, `put_idempotency`). Splitting
the class would touch every import site. Instead, `PostgresBacktestDatabase` implements the
cold-half surface against Neon and **delegates the idempotency methods to an embedded plain
`BacktestDatabase`** (same `DATABASE_PATH` SQLite file, same WAL setup), so the hot path
never gains a network round-trip and no call site changes:

```python
class PostgresBacktestDatabase:
    def __init__(self, database_url):
        self.database_url = require_postgres_url(database_url)
        self._sqlite = BacktestDatabase()      # hot half: idempotency_keys stays local
        self._init_schema()

    def get_idempotency(self, run_id, idem_key):
        return self._sqlite.get_idempotency(run_id, idem_key)
    def put_idempotency(self, run_id, step_index, idem_key, ack):
        return self._sqlite.put_idempotency(run_id, step_index, idem_key, ack)
```

Methods spanning both halves operate on both backends: `clear_all()` truncates the five
Postgres tables *and* delegates to the embedded store; `delete_run()` deletes the Postgres
row (children go via FK cascade) and clears any local idempotency rows for that run.

`domain/runs/repository.py` (`RunStore` — `protocol_runs`/`protocol_steps`) is untouched.

### Method surface to port (the contract, enumerated)

Cold-half methods of `BacktestDatabase`, ported 1:1 with identical signatures and return
shapes (dict rows via `psycopg.rows.dict_row`, mirroring `sqlite3.Row` usage):

- Writers: `insert_run`, `update_run_baselines`, `insert_equity_points` (+ the single-point
  variant), `insert_trades`, `insert_decisions`, `insert_run_manifest`, `delete_run`,
  `clear_all`.
- Readers: `get_run`, `get_run_with_session`, `get_all_runs`, `get_runs_by_session`,
  `get_runs_by_sessions`, `get_runs_by_mode`, `get_equity_curve`, `get_trades`,
  `get_decisions`, `get_run_manifest`, and any remaining cold-half accessors enumerated
  during implementation (the implementing plan lists the exact set from the class).

Dialect-neutral pure helpers (row shapers, ID formats) are imported from `database.py`, not
reimplemented — same reuse rule as the four existing twins.

## Postgres schema

DDL targets the **post-migration** SQLite shape (i.e. what `_migrate_schema` produces),
translated:

- `agent_runs`: as today incl. `session_id DEFAULT 'legacy-demo-session'`, `llm_model
  DEFAULT 'rule-based'`, `baseline_djia_run_id`, `baseline_buyhold_run_id`, token/cost
  columns, `metadata TEXT` (JSON; NULL-tolerant — the protocol path never populates it).
  `created_at`/`updated_at` stay `TEXT`, populated app-side in SQLite's
  `CURRENT_TIMESTAMP` format (`YYYY-MM-DD HH:MM:SS`, UTC) — the twin-precedent shape
  (`users_postgres.py` stores TEXT via `_utcnow_iso()`), keeping read shapes identical.
- `equity_timeseries`, `trades`, `backtest_decisions`: as today, with **real, enforced FKs**
  `REFERENCES agent_runs(run_id) ON DELETE CASCADE`. SQLite declares these FKs but never
  enforces them (no `PRAGMA foreign_keys=ON` anywhere); Postgres enforces by default, and
  CASCADE both simplifies `delete_run` and prevents dangling children.
- `backtest_decisions` additionally gains `actions_trace_ref TEXT` (nullable, unused — the
  reserved R2 seam per Decision 4).
- `run_manifest`: as today.
- Indexes ported 1:1 (`idx_agent_runs_session`, `idx_agent_runs_session_mode`,
  `idx_run_timestamp`, `idx_trades_run`, `idx_decisions_run`).
- Every twin carries the institutional-memory comment block: **"ADDING A COLUMN LATER? It
  must go in an `ALTER TABLE … ADD COLUMN IF NOT EXISTS` below, not just the CREATE"** — with
  the cross-reference to `repository_postgres.py`'s explanation of why nothing else catches
  the omission.

### Dialect-sensitive idioms (verified against the code)

1. **`INSERT OR REPLACE` → `INSERT … ON CONFLICT … DO UPDATE`.** Three call sites:
   `insert_run` (conflict key `run_id`, database.py:401), `insert_equity_points` (key
   `(run_id, timestamp)`, database.py:448/467), `insert_run_manifest` (key `run_id`,
   database.py:776). This is load-bearing for the daily leaderboard: `force_refresh` re-runs
   a deterministic `run_id` (`lb_<strategy>_<start>_<end>`) and relies on overwrite
   idempotency. A literal REPLACE port (delete+insert) would violate the now-enforced FKs
   from surviving `equity_timeseries` rows. True upsert avoids the delete entirely.
2. **`created_at` is preserved on upsert** — deliberate divergence. SQLite's REPLACE
   delete+insert resets `created_at` on every `force_refresh` because `insert_run`'s column
   list omits it; that is accidental, nothing reads it as "last refreshed", and `updated_at`
   exists for that. The upsert's `DO UPDATE SET` clause simply doesn't touch `created_at`.
   Mirror tests assert this as a named exception, not a parity bug.
3. **`trades` / `backtest_decisions` are append-only plain INSERTs** (autoincrement ids;
   written once per run at finalize) — ported as plain INSERTs; Postgres `id` columns use
   `BIGINT GENERATED BY DEFAULT AS IDENTITY`.
4. **Batch writes keep the one-connection-one-commit-per-method shape** using psycopg3
   `executemany` (pipelined) — explicitly not connect-per-row, which would be the plausible
   copy-paste regression from the low-write twins' per-call-connection recipe.
5. **No cross-method transaction is introduced.** Finalize's four writes are independent
   commits today (run row, equity, trades, decisions), with `status='completed'` flipped
   before the baseline block and baseline failures swallowed-but-printed. Postgres keeps
   exactly those semantics — changing atomicity is out of scope and would alter observable
   failure behavior.
6. `psycopg` connections are context-managed (`with conn:` commits/rolls back), dict_row
   factory, per-call `psycopg.connect()` to the **pooled `-pooler` URL** — same as the four
   existing twins.

## Performance trade-offs (accepted, with eyes open)

- **Write load fits the per-call-connection recipe** because the hot half stayed local: a
  run's finalize is ~10–14 pooled connections total (4 main writes + two baseline write
  sequences + baseline-pointer update); a full daily leaderboard refresh is ~2 per strategy.
  Nothing is per-step.
- **The one latency-sensitive moment:** finalize executes inside the final decision-submit
  request, so a Neon cold-start can add seconds to that last ack. Accepted: the 30s decision
  deadline provides headroom, and the daily refresh job (the main recurring writer) is a
  batch context where latency is irrelevant.
- **Reads move to the network**: `GET /runs` and `/api/v2/leaderboard` are full-table scans
  on a public route; fine at current scale (tens of rows), noted as the place pagination
  lands if the table ever grows hot. The known `list_agents_with_stats` N+1 becomes N network
  queries — pre-existing, filed as a follow-up (batched sibling already exists to copy).
- **Neon CU-burn**: the cold half's request profile (batchy, bursty, idle most of the day) is
  the friendly case for scale-to-zero. The DBOS-spike CU measurement from the tech-stack
  blueprint is unaffected by this change.

## Migration, seeding & rollout

Order matters; each step is verifiable before the next:

1. **Provision** — done 2026-07-20: Neon project `ATL-runs-main` (Postgres 18.4, empty).
   Credential verified working; lives in Render env config only.
2. **Set `RUNS_DATABASE_URL` in the Render dashboard *before* merging** (same discipline as
   `CONTENT_DATABASE_URL`): unset silently selects ephemeral SQLite, and the only tripwire is
   the startup line. Use the pooled (`-pooler`) connection string.
3. **Merge → auto-deploy → verify** the log line: `run history backend: postgres
   (ep-…-pooler…/neondb)`. Wrong/typo'd URL shows up here (host/db named, credentials never).
4. **Backfill** — one-time idempotent script `dashboard/scripts/backfill_runs_to_postgres.py`:
   reads a SQLite file (default: the committed seed DB), upserts `agent_runs` (17 rows) and
   `equity_timeseries` (2,585 rows) plus any rows in the other three tables (currently zero)
   into `RUNS_DATABASE_URL`. Idempotent by construction (same upserts as the twin), safe to
   re-run. Until it runs, prod's `/runs` listing is empty — run it immediately after the
   first green deploy. The 3 `defaults.json` demo run IDs ride along (they're vestigial to
   the frontend but remain in the public listing).
5. **#145 unlock (the payoff):** an off-instance scheduler (GitHub Actions cron per fleet
   plan D4) can now run `refresh_daily_leaderboard.py` with `RUNS_DATABASE_URL` pointed at
   the same Neon project, and prod serves what it writes. Wiring that cron is issue #145's
   own PR, not this one.

Local dev and the test suite are untouched: `RUNS_DATABASE_URL` unset → SQLite exactly as
today; `tests/conftest.py` strips the new var at import time alongside the other two.

## Testing

Same three-tier structure as the #134/#136/#137 net:

1. **Ordinary CI (SQLite)** — existing suite must stay green untouched; plus `capsys` tests
   for both startup lines (never `caplog`), and a factory test that `RUNS_DATABASE_URL`
   selection + stripping behaves like its two siblings.
2. **`@pg_only` tier (live Postgres, runs in CI via the existing `postgres:18-alpine`
   service + `TEST_POSTGRES_URL`)** — mirror parity suite running the same behavioral
   assertions against `PostgresBacktestDatabase`: round-trip every ported method; the three
   upsert paths (incl. leaderboard-style re-insert of an existing `run_id` with equity rows
   present — the FK-sensitive case); `created_at` preservation as the named divergence; FK
   cascade on `delete_run`; `executemany` batch inserts; delegation (idempotency calls land
   in SQLite, never Postgres). **The new destructive fixture MUST call
   `require_local_postgres_url()` before any `DELETE FROM`** — the standing 5th-fixture
   convention from #136 — and joins `test_postgres_url_guard.py`'s parametrized fixture list
   so ordinary CI proves the guard fires.
3. **Coverage-net wiring** — the new module follows the `TEST_POSTGRES_URL`-at-import
   `pg_only` marker pattern, which fails open (skips) when unset; `test_ci_postgres_wired`
   already makes that loud in CI, and the new tests ride the same net.

Backfill script gets its own test: seed-fixture SQLite → in-test Postgres → row counts +
spot-checked parity + re-run idempotency.

## Config & docs surface

- `.env.example`: add `RUNS_DATABASE_URL` with a one-line comment.
- `render.yaml`: add `RUNS_DATABASE_URL` (`sync: false`) beside `USERS_DATABASE_URL` /
  `CONTENT_DATABASE_URL`.
- `CLAUDE.md`: extend the env-var bullet list; fix the now-ambiguous "Persisted stores
  (protocol runs, strategies) live in this DB" line; update the "Prod deploy reality" bullet
  (run history no longer evaporates once this ships).
- `2026-07-15-agent-strategy-persistence-design.md`: no edit (historical record), but this
  spec is its named phase-2 successor.

## User-facing docs made true/stale by this change (follow-ups, not edited mid-session)

- `README.md:81` and `docs/architecture/dashboard-target-structure.md:213` — file-structure
  diagrams say `storage/ # backtest.db` without distinguishing what now lives in Postgres;
  needs a note once this ships.
- The 7-doc durability list from the 2026-07-15 spec (lines 418–430) — those docs promised
  agent durability (now true); run-history durability claims should be re-checked once this
  lands.

## Out of scope (follow-up issues, filed at merge time)

1. **Hot half durability** (`idempotency_keys`, `protocol_runs`, `protocol_steps`) — needs
   its own latency design (write-behind/batching vs per-step round-trips vs coarser
   snapshots). #140 stays open as the tracker until decided otherwise.
2. **Broken `/paper/start-session` run insert** — `api/routers/paper_trading.py:273` omits
   the required `session_id` arg; the TypeError is swallowed. Pre-existing; also noted in the
   fleet wiring plan.
3. **`list_agents_with_stats` N+1** — add a `get_runs_by_sessions`-batched path (the builtin
   sibling already has one).
4. **`agent_runs.metadata` inconsistency** — `external_run_service._finalize()` never passes
   `metadata=`, so protocol runs carry NULL provenance while engine runs don't.
5. **R2 `actions_trace_ref` offload** — when protocol-run volume materializes.
