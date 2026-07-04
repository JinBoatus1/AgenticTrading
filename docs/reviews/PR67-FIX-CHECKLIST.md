# PR #67 Fix Checklist — "Major Platform and Architecture Update"

Source: 91-agent adversarial review, 2026-07-03. PR by Allan-Feng, 292 files, +30k/−4.9k, CONFLICTING.
73 findings confirmed (dedup'd below): **1 critical, 8 high, ~18 unique medium, ~24 low**.

**Bottom line:** the *package refactor* is sound and near-shippable; nearly every bug is in the *new features* bolted alongside (Protocol v1, SDK, Discord, strategy store, built-in agents, landing page, leaderboard models). Recommend splitting refactor from features. Fix order below is roughly merge-priority.

> **STATUS (2026-07-04):** 🔴 BLOCKERS **B0/B1 DONE + pushed** (`d62f976`). 🟠 **ALL HIGH H1–H9 DONE + PUSHED** to PR #67 — PR head is now **`9268da8`** (clean fast-forward `d62f976..9268da8`, no force; commits `50e0d95`, `472b127`, `970d5db`, `95bca5f`, `a4f6362`, `8974788`, `5fd64c3`, `9268da8`) — each red-green + full-suite gated + adversarially reviewed. Fresh pre-push regression on the pushed tree: backend 5 failed (pre-existing) / 647 passed / 2 skipped; packaging 36 passed. 🟡 Medium + ⚪ Low: untouched. **Heads-up (still open):** the new CI runs the full suite → RED on the 5 pre-existing failures (4× `test_backtest_isolation`, 1× `test_prompt_contains_constraints`) until they're xfail'd/fixed. PR still shows `CONFLICTING` = pre-existing `/api/v1` vs `/api/v2` base conflict, not from our push.

## Working setup for the fix session

- PR worktree already checked out at `/tmp/pr67` (branch `pr-67-review`, head `b523401`). Diff base = merge-base `e24fe80`.
  - PR diff of a file: `git -C /tmp/pr67 diff e24fe80 HEAD -- <path>`
  - Pre-PR version: `git -C /tmp/pr67 show e24fe80:<path>`
- Tests: `~/atl-venv/bin/pytest` (needs `matplotlib==3.11.0` + `pytest-timeout` installed; run with `DATABASE_PATH=/tmp/atl_test.db` and `--timeout=180` because the suite currently HANGS — see B0). Restore the seed DB after: `git -C /tmp/pr67 restore dashboard/storage/data/backtest.db`.
- Full findings record: Central DB `knowledge/atl-pr67-review.md`.

---

## 🔴 BLOCKERS

### B0 — Test suite never terminates + 6 new failures — ✅ DONE (in PR #67, commit `d62f976` on `83c0af38`, 2026-07-04)
**Corrected root cause:** NOT the event-loop diagnosis originally written below. The hang was `AlpacaDataLoader._load_credentials()` → `sys.exit(1)` when Alpaca creds are absent → `SystemExit` (a `BaseException`) escaping `_finalize()`'s `except Exception`, wedging the ASGI request future forever (only the two completion-driving protocol tests reached it). Fix = catch `SystemExit` in the best-effort baseline block; also converted `/api/v1/runs` handlers to sync `def` (defensive — closes the original event-loop concern too). Adversarial review surfaced a **sibling with the same bug class** — `start_backtest()`'s background market-data loader (`external_run_service.py:722`) — now also fixed (would otherwise strand a run in `"loading"` forever). **Result: 5 failed / 610 passed / 2 skipped, terminates in ~20s with NO `--timeout`.**
- [x] Fix the deterministic hang (`test_timeout_generates_hold`, `test_full_run_to_completion_and_result`) — via the `SystemExit` catch + sync handlers above. Verified `pytest tests/` finishes with NO `--timeout`.
- [x] Update 3 stale route-contract tests — added `/favicon.ico`, `/runs/{run_id}/plot.png`, `/v1/agents/builtin` to the `EXPECTED_*` sets in `tests/test_app_composition.py` and `tests/test_router_move.py`.
- [x] Fix `tests/backtesting/test_canonical_consumers.py` — now asserts `make_llm_client` (Anthropic re-export removed).
- [x] Make packaging tests runnable out-of-the-box — added `pythonpath = ["src"]` to `packaging/agentictrading/pyproject.toml`.
- [x] Added a CI workflow (`.github/workflows/ci.yml`) running `pytest` for backend + packaging.

### B1 — CRITICAL: unauthenticated takeover of any built-in agent — ✅ DONE (in PR #67, commit `d62f976` on `83c0af38`, 2026-07-04)
`api/routers/agents.py`. Independent adversarial review verdict: **FIX-SOUND — all three vulns closed, no working bypass found.**
- [x] Stop returning `session_id` from the public `GET /api/v1/agents/builtin` listing.
- [x] Stop treating `session_id` as an ownership credential — removed the `session_id` branch in `owns_agent` and `require_access`. (Also fixed `owns_agent` to read `owner_user_id`/`owner_browser_session` straight from the DB row — `_public_agent` had dropped `owner_browser_session`, so legit owner-session auth never actually worked and the insecure `session_id` branch was silently the *only* path.)
- [x] Require real owner context OR the agent's own API key on state-changing routes (`DELETE /{id}`, `POST /{id}/rotate-api-key`). API-key path verified scoped to that agent — a key for agent A cannot act on agent B.
- [x] IDOR fail-open — `_require_run_owner` now DENIES when `agent_id` is null. **Red-green-verified regression test added** (`test_orphaned_run_denied_fail_closed`): confirmed 403 with fix, 200 without.
- [x] Regression tests added (anonymous `/builtin` leak, `X-Session-Id` replay → 403 on delete/rotate, api-key path); corrected existing tests that codified the vulnerable `session_id`-as-credential behavior.

### Follow-ups surfaced by the B0/B1 adversarial review (not blockers; fold into later work)
- [ ] **Systemic `sys.exit()`-in-background-thread class** — the same pattern still exists at `app.py:150` (paper-baseline init), `api/routers/backtests.py:301` (legacy `/backtest/run`), and `domain/backtesting/algo_service.py:377` ("My Trading Algo"). Cleanest fix = stop `AlpacaDataLoader`/`BaselineGenerator` calling `sys.exit()` at all (raise a normal exception; handle at the CLI boundary). Overlaps **H4**'s run-lifecycle reaper.
- [ ] **`_owner_context` session_id fallback** (`api/dependencies.py:34-44`): when `X-Browser-Id` is absent, `browser_session` falls back to `X-Session-Id`, and `import_session` sets `owner_browser_session = session_id` — so for *import-created* agents, `session_id` IS the credential. Does NOT affect built-in agents or cross accounts (not the B1 hole), but "session_id is never a credential" isn't a blanket invariant — add a comment / revisit.
- [ ] **CI `DATABASE_PATH` backstop** (`.github/workflows/ci.yml`): CI relies on `tests/conftest.py`'s `tempfile.mkdtemp()` self-isolation; there's no explicit CI-level `DATABASE_PATH`. Add one as belt-and-suspenders.

---

## 🟠 HIGH

### H1 — Strategy store data-loss on every Render deploy — ✅ DONE (commit `970d5db`, 2026-07-04)
`domain/strategies/repository.py:23`
- [x] Moved the strategy store into a `strategies` table in the main DB (`DATABASE_PATH`, on Render's persistent disk) — JSON file lived under ephemeral `DATA_DIR`, wiped every deploy. Follows the `RunStore` pattern (lazy `_init_schema`). Public API (`create_strategy`/`get_strategy`/`set_last_run`) preserved; record shape byte-identical (verified field-by-field). SQLite locking → genuinely cross-process safe (resolves the docstring L); `set_last_run` kept & wired. Two `/api/strategies` endpoints flipped `async def`→`def` (blocking I/O off event loop). Adversarial verify (sonnet): migration sound; fixed its finding (code-collision now widens the space like the old fallback instead of raising a 500).
- Tests: +8 (tests/domain/strategies/test_strategy_store.py) incl. persistence-across-instances + lands-on-DATABASE_PATH + router TestClient. Suite: 5 failed (pre-existing) / 630 passed / 2 skipped. No JSON migration (old file never committed, ephemeral).

### H2 — Protocol advertises constraints it never enforces — ✅ DONE (commit `50e0d95`, 2026-07-04)
`domain/runs/service.py:379`
- [x] In `submit_decision`: validate `order.symbol` against `constraints()['allowed_symbols']` (was hardcoded DJIA_30, ignored a narrower config.symbols); reject decisions exceeding `max_orders` (400 `too_many_orders`, raised before finalize so step stays re-submittable); enforce `max_position_weight` per order against equity.
- [x] `create_run`: reject a non-default `config.initial_cash` with `invalid_config` (SDK default 100000 still passes); `config.symbols` is now honored as the tradeable allow-list (already validated ⊆ DJIA_30).

### H3 — One oversized order voids the whole decision & burns the step — ✅ DONE (commit `50e0d95`, 2026-07-04)
`domain/runs/service.py:398`
- [x] Over-cap / over-ceiling orders are pre-filtered into per-order rejections BEFORE the engine's all-or-nothing batch validator, so valid siblings still execute. `OrderIn.quantity` Field now `allow_inf_nan=False, lt=1e12`.
- [x] **Deeper than the checklist assumed — 2 defects found by an adversarial refute panel (3 sonnet agents) and fixed in the same commit:** (1) `allow_inf_nan=False` alone still 500'd because FastAPI echoes the `inf` input into the 422 body and Starlette's `JSONResponse(allow_nan=False)` crashed serializing it → added an app-wide `RequestValidationError` handler that sanitizes non-finite inputs (`app.py`). (2) intra-decision accumulation bypass (N buys of same symbol each saw existing=0 → collectively breached cap) → now tracks per-symbol pending shares. (3) engine's hard 10k-share cap (`validator.py` `LLMTradingDecision`) still voided the whole batch for a low-price over-ceiling order → pre-reject as `exceeds_max_order_size` (`MAX_ORDER_SHARES` extracted as shared constant). Constraint values coerced defensively (bad env type → unenforced, not 500).
- Tests: +8 protocol tests, all red-green verified. Suite: 5 failed (pre-existing) / 617 passed / 2 skipped.

### H4 — Run lifecycle can't recover + blocking work on event loop — ✅ DONE (commit `472b127`, 2026-07-04)
`domain/runs/service.py:40,271` + `api/routers/runs.py:125`
- [x] **Blocking work on event loop — already resolved by B0.** Handlers are `def` (threadpool); `_finalize()`'s two baseline backtests run under `_step_lock`, reached only from `def` handlers / the background loader — never the event loop. Verified; no further change needed.
- [x] Reaper + recovery: background daemon (`start_reaper`) drains abandoned runs through elapsed deadlines and evicts terminal runs' engine **session only** (frees market-data buffers, ~99% of the memory); startup `recover_orphaned_runs` marks crash-orphaned `running` rows failed (gated by `RUN_RECOVERY_ON_STARTUP`, single-process assumption); per-agent concurrent-run cap (`MAX_ACTIVE_RUNS_PER_AGENT`, lock-guarded → race-safe, 429).
- [x] Idempotency replay scoped to `(step_id, key)`. `_get_run` double-checked under lock.
- [x] **Adversarial refute panel (3 agents) caught a self-inflicted regression:** the first cut evicted the whole `ProtocolRun`, breaking GET `/steps/{id}` (404), `/steps/next` (409) and idempotent retry (409) after eviction. Fixed by keeping the lightweight ProtocolRun (step-id map + idempotency cache) and answering next-step from persisted state when the session is gone. Also hardened: recovery/reaper split try/except; recovery multi-worker caveat documented + env-gated.
- [ ] **DEFERRED (documented):** cross-restart DB persistence of step_id↔sequence + idempotency map. Low value (engine sessions don't survive a restart → those runs are failed by recovery anyway); only historical step-id queries *after a full restart* are affected. Larger schema change, better done deliberately. → tracked as a follow-up.
- Tests: +5 protocol tests, all red-green verified. Suite: 5 failed (pre-existing) / 622 passed / 2 skipped.

**H4 follow-ups (not blockers):** cross-restart step/idempotency persistence (above); `_runs` no longer shrinks (ProtocolRuns kept for reads — small, but a slow growth; revisit with the persistence work); multi-worker recovery hardening (instance-id/heartbeat instead of blanket UPDATE) if the deployment ever goes multi-process.

### H5 — SDK AgentRunner aborts the whole run on the 30s decision deadline — ✅ DONE (commit `95bca5f`, 2026-07-04)
`packaging/agentictrading/src/agentictrading/runner.py:124-135`
- [x] Catch `ATLConflictError` with code in `{decision_deadline_exceeded, step_already_finalized}` around `submit_decision` and advance (step auto-held, run live). `on_execution_result` skipped for the auto-held step.
- [x] Attach `run.id` to every backend error in `run_backtest` (`ATLAPIError.with_run_id`, preserves traceback); documented the 30s window in the README. Validate `poll_interval > 0` (0 was a real busy-loop: `_wait`'s `sleep_for or poll_interval` fallback never advanced the idle timer). `max_steps` exit returns metrics (status "running") not a `/result` 409.
- [x] **Adversarial verify (sonnet) found a latent landmine:** a real late decision surfaces as `step_already_finalized`, NOT `decision_deadline_exceeded` (backend applies the auto-hold in `get_status` before re-checking the step) — the catch-set covers it, but nothing locked which code the backend emits (SDK tests fabricate the string). Added a cross-package backend contract test `test_late_decision_returns_autoheld_code` + cross-referenced comments so a future cleanup can't silently regress H5.
- Tests: +6 SDK runner tests (red-green verified) + 1 backend contract test. packaging: 36 passed. backend: 5 failed (pre-existing) / 631 passed / 2 skipped.

### H6 — Leaderboard publishes rule-based curves under LLM model names — ✅ DONE (commit `a4f6362`, 2026-07-04)
`domain/leaderboard/service.py:196`
- [x] `_reject_if_llm_fallback`: refuse to publish when `strategy_impl.used_llm` is False OR `llm_calls == 0`, unless `allow_fallback=True` / `--allow-fallback`. Applied on BOTH insert paths (`deploy_model_run` + `ensure_leaderboard_runs`) so a misconfigured LLM entry on the auto-compute path can't bypass it. Baselines expose no `used_llm` → untouched. CLI prints + exits non-zero on refusal.
- [x] `llm_agent.py:88` now uses gateway-aware `default_model_name()` for the default model id (native vs CommonStack slug).
- [~] **Full model_id↔gateway reconciliation NOT realized (documented, deployment-gated):** every configured entry sets an explicit `model_id`, so `default_model_name()` is dead code for them; and the 4 non-Anthropic entries (gpt/gemini/deepseek/qwen) physically can't run on an Anthropic-only key (they need CommonStack). No code fixes that — it's an ops/key decision. The guard now makes those entries **refuse** rather than publish fakes, which is the correct outcome.
- [x] **Adversarial verify (sonnet):** guard sound — only 2 insert paths (both guarded); no false positives (all-HOLD LLM run has `llm_calls>0` — counter is per completed call, not per trade); no false negatives (per-request model rejection → `used_llm=True/llm_calls=0` → caught).
- Tests: +7 (red-green verified) + updated canonical-import test. Suite: 5 failed (pre-existing) / 638 passed / 2 skipped.

**H6 operational follow-up (not a blocker):** the guard fires on new writes only — any fallback published *before* this patch keeps serving from cache. Re-run `deploy_leaderboard_model.py --entry <id> --force` for each LLM entry once after this ships to flush stale fallbacks.

### H7 — Discord bot forwards the `local-model` sentinel as a real model id — ✅ DONE (commit `8974788`, 2026-07-04)
`integrations/discord_bot.py:303`
- [x] Added `token_cost.is_free_model()` (reuses `_FREE_MODEL_MARKERS`); `discord_bot._model_override()` maps a sentinel/rule-based/empty model_name → `None` at BOTH forwarding sites (`/ask` → `chat_with_agent`, `/backtest` → payload). Real model ids pass through. `chat_with_agent` already treats `model=None` as "use default". Verified only 2 API-forwarding sites exist.
- Tests: `is_free_model` unit tests + behavioral `_model_override` test (guarded by `importorskip('discord')`, runs where the dep is present) + a source-level wiring guard (`tests/integrations/`) that runs everywhere (discord is an undeclared optional dep → behavioral test skips in base env). Red-green verified. Suite: 5 failed (pre-existing) / 642 passed / 2 skipped. (Self-verified rather than a dedicated adversarial agent — trivial sentinel-mapping, no subtle logic. The `discord.py`-dep-undeclared item stays a separate MEDIUM.)

### H8 — Frontend shows fabricated data to real users — ✅ DONE (commit `5fd64c3`, 2026-07-04)
`frontend/app.js:423` + `frontend/js/portfolio.js:15`
- [x] `MOCK_AGENTS` gated behind `isDemoMode()` (`?demo` flag or localhost/127.0.0.1/file host). Production users get the real empty-state; an API failure shows a distinct error-state (`renderAgentsError` + `#agentsErrorState`) instead of fake agents.
- [x] Added a prominent "SAMPLE DATA" badge to the "My Portfolio" heading (mock is clearly labeled, not a real account). Full `/paper/*` wiring left as a larger feature; the badge makes the current mock honest.
- Verification (no JS harness): `node --check` both files; a node behavioral check of the extracted `isDemoMode` across 7 host/query cases (prod→false, localhost/`?demo`→true, `?demo=0`→false); source-guard tests (`tests/integrations/test_frontend_no_mock_data.py`) that run in CI, red-green verified. Suite: 5 failed (pre-existing) / 645 passed / 2 skipped.

### H9 — Published run command is broken + docs contradict the restructure — ✅ DONE (commit `9268da8`, 2026-07-04)
`docs/source/lab/getting_started.rst:63`, `app.py:279`
- [x] `getting_started.rst` now documents `uvicorn dashboard.backend.app:app --reload` / `python -m dashboard.backend.app` (dropped the broken `python3 dashboard/backend/app.py`). `dashboard-target-structure.md` note updated. **`app.py` `__main__` block was already correct** (`uvicorn.run` with the canonical import string — a real `python -m` entrypoint) → left as-is, not deleted.
- [x] Shipped a root `CLAUDE.md` on the PR branch (it had none) documenting the **package contract** (`dashboard.backend.*` imports, uvicorn run cmd, api/routers + domain/* layout). Header note flags it **supersedes main's flat-imports CLAUDE.md and must win at merge** — the "coordinate with main" reconciliation (same class as the `/api/v1` vs `/api/v2` merge decision).
- Tests: doc-guard tests (`tests/integrations/test_docs_run_command.py`), red-green verified. Suite: 5 failed (pre-existing) / 647 passed / 2 skipped.

---

## 🟡 MEDIUM (deduplicated)

> **STATUS (2026-07-04):** 🟡 **ALL actionable MEDIUM items DONE** on `pr-67-review` (11 items + a 10-agent adversarial pass + a 2nd round fixing every confirmed defect it found). Commits `525e7fe..3986d40` (local only — **not pushed**). Full regression: backend 5 failed (pre-existing) / **704 passed** / 2 skipped; packaging **39 passed**. Deferred (user decision): **#1** v1/v2 reconciliation and **#10** landing rebuild.

- [ ] **Reconcile `/api/v1/runs` vs already-merged `/api/v2`** — **DEFERRED** (user decision, own session). The substantive core of the merge conflict; do NOT publish `agentictrading` 0.2.0 or ship both peer surfaces meanwhile.
- [x] **Anonymous `/backtest/run` cost abuse** — ✅ `ce4a690` + `b3949f2`/`ca176a2`. Prompt cap (4000), date-range cap (≤31d), model-id **format** validator, per-client rate limit. Adversarial pass caught that a pricing-table allowlist 422'd the UI's own dropdown models → switched to a charset/length validator; is_known_model removed. Rate limit is best-effort (self-minted-header key is rotatable) — the per-request caps are the hard limits; expensive models are an intentional product offering (UI lists opus), so no tier cap.
- [x] **`/runs/{run_id}/plot.png` blocks the loop** — ✅ `ac8bfd8` + `34d50b4`. Sync `def` (threadpool), module-level matplotlib (Agg), `@lru_cache` per run_id (404s not cached). Adversarial pass caught that `ext_<second-timestamp>` run_ids collide under INSERT OR REPLACE → made the cache premise true by adding a uuid8 suffix to ext_ run_ids (also fixes #8). Stays session-exempt by design (it's an `<img>` embed).
- [x] **`POST /api/strategies` unauth unbounded write** — ✅ `5839bdf` + `ca176a2`/`dbdc96f`. prompt `max_length=5000`, per-client write rate limit (new reusable `api/rate_limit`), `owner` documented display-only. Adversarial pass caught the limiter's dead memory-reclaim branch (added a bounded sweep) and that the Discord bot shared one IP bucket (bot now sends per-user `X-Browser-Id`).
- [x] **`/app/` trailing-slash serves broken page** — ✅ `525e7fe` + `8257d12`. 308 redirect to `/app`, **preserving the query string** (deep-links `?auth=login` etc.).
- [x] **`strategy.html` uses `location.origin` as API base** — ✅ `5d2c511` + `07050c5`. Replicates app.js's localhost-vs-onrender resolution; date defaults now formatted from **local** parts (not UTC toISOString off-by-one).
- [x] **Silent strategy rewrite inside "verbatim" extraction** — ✅ `948884d` + `e55d0d0`. Docstring corrected to disclose the safe_trading RSI→trend ranking change (without over-attributing it to the move); +3 characterization tests (trend ranking, holdings-append isolated to rsi=50, NaN bars).
- [x] **`decision_deadline_exceeded` is dead code** — ✅ `7062787`. `submit_decision` consults the engine decision log (`_step_decision_source`); a deadline auto-hold now raises `decision_deadline_exceeded`, a genuine double-submit keeps `step_already_finalized`. H5 backend contract test tightened; SDK NOTE corrected.
- [x] **Protocol doc/impl mismatches** — ✅ `4c83027` + `ebda441`. Dropped phantom `cancelled` state; all runs.py 4xx go through `error_body()`; §11 completed with the actually-emitted codes (`forbidden`, `agent_version_not_found`, `unsupported_environment`, `result_not_found`, `too_many_active_runs`, `run_failed`, mismatch codes). +doc-guard tests.
- [ ] **Landing build artifacts stale + unbuildable** — **DEFERRED** (needs npm/vite tooling; heavier, own session).
- [x] **Discord `discord.py` dep undeclared** — ✅ `c658de4` + `3986d40`. Declared in `requirements-discord.txt` (mirrors `requirements-sphinx.txt`), now self-contained via `-r requirements.txt`; CLAUDE.md updated; source-guard test.
- [x] **SDK `initial_cash` ignored by backend** — ✅ `08f43b4` + `75863f3`. Param defaults None; a non-default (via kwarg **or** raw `config` dict) is rejected client-side (`initial_cash_fixed`) and never sent; dropped from README/quickstart/protocol-config/all 4 examples.
- [x] **Add tests for changed behaviors** — ✅ `e5373db` (+ folded into per-item TDD). NaN-bar ranking + `strategy_prompt`→`create_prompt` wiring; plot.png/strategies TestClient tests; protocol deadline/envelope tests. (`default_model_name()`/`make_llm_client()` env-matrix stays with H6's gateway work.)

---

## ⚪ LOW (batch sweeps — cheap wins)

- [ ] **Docstring sweep**: `grep -rn "compatibility re-export shim" dashboard/backend --include=*.py` — 17+ moved modules claim shims that were deleted in Phase 4A. Rewrite to "original module removed in Phase 4A" (agents/backtesting/leaderboard/runs repositories + services).
- [ ] **Vercel caching**: `vercel.json:25,33` serves content-hashed `/assets/*` with `max-age=0` — set `public, max-age=31536000, immutable`; keep no-cache only on mutable entry points (index.html/app.js/styles.css).
- [ ] **favicon**: `app.py:173` `/favicon.svg` returns PNG bytes and shadows `frontend/favicon.svg` — serve the real SVG (`image/svg+xml`), keep PNG for `/favicon.ico`, or delete the unused file.
- [ ] **`.env.example:22`** commits a real Discord channel snowflake — replace with a fake placeholder.
- [ ] **`LLM_MAX_OUTPUT_TOKENS`** (`infrastructure/llm/backtest_harness.py:127`) crashes at import on malformed value — parse defensively (fallback 2000); record effective max_tokens in run metadata when it deviates.
- [ ] **SECURITY.md:26** still references pre-move validator paths — update to `dashboard.backend.infrastructure.llm.validator`.
- [ ] **Custom `strategy_prompt` LLM path** (`validator.py:669`) bypasses `validate_llm_response` — route parsed decisions through it (or apply `TradingConstraints` + action-count cap), or document the exemption in SECURITY.md.
- [ ] **`agent_versions.py:92`** existence lookup before auth (oracle) — auth first or return 404 for both not-found/denied.
- [ ] **`/api/v1/agents/builtin` N+1 queries** (`agents.py:94`) — batch the stats lookup / cache the listing.
- [ ] **Rejection `order` shape inconsistency** (`domain/runs/service.py:420`) — always emit the protocol order shape.
- [ ] **Observation has empty bars/events for most symbols** (`domain/runs/service.py:580`) — include features for allowed_symbols or document the truncation.
- [ ] **Delete dead landing components** (`frontend/landing/src/components/hero.tsx` lowercase set) + prune unused `ui/` primitives.
- [ ] **SDK Python 3.9** mid-read socket timeout escapes as raw `socket.timeout` (`atl_client.py:112`); `sdk_quickstart_selftest.py` docstring contradicts its default end date.

---

## Pre-existing (NOT this PR — verified out of scope, but worth a separate ticket)

- `DELETE /admin/clear` wipes the whole DB with no auth (`api/routers/admin.py:15`) — moved verbatim, pre-existing.
- `/paper/*` exposes the Alpaca paper account unauthenticated — pre-existing.
- 6 known baseline test failures (`test_rotate_api_key`, 4× `test_backtest_isolation`, `test_prompt_contains_constraints`).

## What NOT to touch (verified faithful — don't "fix" these)

LLM `validator.py` moved byte-for-byte (enforcement intact); module-identity guards pass; legacy flat routes verbatim with `filter_market_hours` + session isolation; `ag_` key scheme, portfolio math, Alpaca paper-only URLs, decide-at-t/execute-at-close timing all preserved.
