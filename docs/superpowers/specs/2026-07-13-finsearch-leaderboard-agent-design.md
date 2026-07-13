# Agentic FinSearch as a Leaderboard Trading Agent (Plan 3) — Design Spec

- **Date:** 2026-07-13
- **Owner:** Felix (FlyMiss)
- **Repos:** agent-trading-lab (provider + entry) **and** Agentic-FinSearch (trader personality)
- **Status:** Design — written under the AFK planning loop; open forks decided with rationale below and flagged for Felix's review in the PR
- **Programme:** Plan 3 of 3 (Plan 1 = news→signals, sibling spec `2026-07-13-finsearch-news-signals-panel-design.md`; Plan 2 = agent-API foundation, shipped)
- **Precedent:** the six-LLM leaderboard onboarding (PRs #72/#74/#75) and the freshest add-a-model example, PR #96 (OpenRouter Nemotron) — this spec deliberately follows that recipe.

## 1. Goal

Agentic FinSearch (AF) trades the leaderboard contest **exactly like the other model entries**: same `LLMAgentStrategy` loop, same prompt, same H6 integrity guard, same contest window (2026-04-15 → 2026-05-15, 161 hourly decision steps), same deploy path (`deploy_leaderboard_model.py` → seed-DB commit). Once the run lands, the frontend displays "Agentic FinSearch" with **zero frontend changes** (rendering is fully data-driven — verified: `leaderboard.js` has no name-keyed logic; unmatched labels get auto-assigned palette colors).

AF today has no trading behavior and no "professional trader personality." Both are added: the personality lives in **AF's repo** (it is AF's product surface, reusable beyond ATL); the integration shim lives in **ATL** (a provider module, like OpenRouter's).

## 2. Approaches considered

| Approach | Verdict | Why |
|---|---|---|
| **A. ATL provider module over AF's OpenAI-compatible `/v1/chat/completions`** | **Chosen** | "Just like other models" literally: a fourth sibling in `infrastructure/llm/providers/` (`commonstack`, `openrouter`, `anthropic` exist). Reuses the entire proven pipeline — prompt, parsing, counters, H6, deploy, display. Smallest new surface; PR #96 is a 1:1 template. |
| B. AF as an external agent driving `/api/v2` protocol runs | Deferred (future benchmark phase) | This was Plan 3's original sketch, but v2 runs don't feed the leaderboard contest table, "like other models" points at the provider path, and the full agentic value of it only materializes with live/paper mode (Phase B — not built). Revisit when Phase B lands; see §8. |
| C. Add AF's underlying foundation model directly via an existing provider | Rejected | Measures Gemini/GPT, not AF. No AF surface involved — defeats the goal. |

## 3. The integrity fork (the one hard problem)

AF's default `/v1` modes (`thinking`, `normal` — currently identical) attach the **full 46-tool live catalog** (yfinance, TradingView, SEC EDGAR, web scrape, Playwright) with `max_turns=30`. In a **backtest over past dates**, live tools are **structural look-ahead**: the agent can read July's prices/news while "trading" April 15th. Every other leaderboard model sees only the prompt's market snapshot; an AF entry with live tools could not honestly share their board.

**Decision: the leaderboard entry runs AF's *direct, tools-off* path with the trader persona.** AF already has the exact precedent: `Buffet-Agent` skips the agent/tool machinery entirely (`create_agent_response` branches on the provider config) and applies a server-side persona (`BUFFETT_INSTRUCTION`). We generalize that mechanism (config-driven, buffet becomes its first user) and add a **`FinSearch-Trader`** model entry: AF's configured foundation model + AF's professional-trader persona + no tools. That is what "AF the trading agent" *can honestly mean under backtest rules*.

The full agentic AF — tools, research, live data — is the **live paper-trading** story, where "now" data for "now" decisions is legitimate (and where Plan 1's signals feed into the context). That is the programme's stated future and stays out of scope here (§8).

Guardrail (advisor memo, carried through the programme): **measurement, not alpha-seeking** — we are benchmarking an agent's trading behavior on the shared apparatus, not shipping a money-maker.

## 4. AF-side design — the professional trader personality (own PR in Agentic-FinSearch)

### 4.1 Persona mechanism (generalize the buffet branch)

- `MODELS_CONFIG` (`Main/backend/datascraper/models_config.py`) gains a new entry:

```python
"FinSearch-Trader": {
    "provider": "google",                # same family as the FinGPT default (gemini-3-flash-preview);
    "model": "gemini-3-flash-preview",   # final choice at impl time — must be a provider the direct
    "direct": True,                      # (non-agent) path already supports
    "persona": "trader",
    "max_tokens": 1_048_576,
    "supports_streaming": False,
    "description": "Professional trader persona — direct path, no tools (backtest-safe)",
},
```

- `create_agent_response` (`datascraper.py:1015-1021`) currently branches `provider == "buffet"` → direct path. Generalize to `model_config.get("direct") or provider == "buffet"` (buffet keeps working, gains `direct: True` in config as cleanup).
- `_prepare_messages` (`datascraper.py:281-291`) currently branches `provider == "buffet"` → `BUFFETT_INSTRUCTION`. Generalize to a persona registry: `PERSONA_INSTRUCTIONS = {"buffett": BUFFETT_INSTRUCTION, "trader": TRADER_INSTRUCTION}`, selected by `model_config.get("persona")`, falling back to the default `INSTRUCTION`.

### 4.2 The persona text (draft — final wording in the AF PR)

```python
TRADER_INSTRUCTION = (
    "You are FinSearch Trader, a disciplined professional equities trader. "
    "You manage positions with a risk-first process: capital preservation precedes "
    "return-seeking; you size positions to conviction and cut losers rather than "
    "average down into a failing thesis. You reason strictly from the evidence you "
    "are given — prices, technical indicators, portfolio state, and any provided "
    "news — and you never invent data you were not shown. When evidence is mixed "
    "you prefer holding over churning, and you can say why in one or two sentences. "
    "When a request specifies an output format or schema, you follow it exactly: "
    "no extra prose, no markdown fences, no disclaimers."
)
```

Design notes: the persona is **format-agnostic** (the last sentence defers to the caller's requested schema rather than baking ATL's JSON contract into AF) — it stays reusable for any consumer. The "never invent data" clause is the persona-level echo of the no-look-ahead rule.

### 4.3 What the AF PR contains

1. `TRADER_INSTRUCTION` + persona registry + `direct` config flag generalization (buffet migrated onto both, behavior-preserving).
2. `MODELS_CONFIG["FinSearch-Trader"]` entry.
3. Tests mirroring `tests/test_openai_api.py`: `/v1/models` lists the new key; a `FinSearch-Trader` chat completion takes the direct path (no agent/tools — assert via the same seam the buffet tests use), carries the persona, and honors a caller format request end-to-end.
4. Docs: `Docs/source/api_reference.rst` model table gains the entry.

**Not** in the AF PR: any ATL-specific trading schema, any new mode, any change to the agent/tool path.

## 5. ATL-side design — the `finsearch` provider

New sibling module `dashboard/backend/infrastructure/llm/providers/finsearch.py`, registered in `PROVIDERS` (`providers/__init__.py:31-35`). Contract compliance (per `providers/__init__.py:1-13`):

- `INTEGRATION_ID = "finsearch"`; `DEFAULT_MODEL = "FinSearch-Trader"`; `default_model_name()`.
- `make_client(anthropic_cls)` → returns `None` (with printed warning, never raises) unless `FINGPT_API_KEY` is set; otherwise a **shim client** that ignores `anthropic_cls` entirely:
  - `client.messages.create(model=…, max_tokens=…, messages=…, system=None, **_)` →
    `POST {FINSEARCH_BASE_URL}/v1/chat/completions` with
    `{"model": model, "mode": FINSEARCH_MODE (default "normal"), "messages": [system?, …messages]}`,
    `Authorization: Bearer <FINGPT_API_KEY>`, `timeout=150` (AF's gunicorn kills at 120s; the extra margin only classifies the failure client-side).
  - Response → Anthropic-shaped object: `content=[SimpleNamespace(type="text", text=choices[0].message.content)]`, `usage=SimpleNamespace(input_tokens=prompt_tokens, output_tokens=completion_tokens)` — exactly what `extract_response_text` (`backtest_harness.py:163-190`) and `extract_token_usage` (`:192-206`) read.
- Env: `FINGPT_API_KEY` (shared with Plan 1 — one secret), `FINSEARCH_BASE_URL` (default `https://agenticfinsearch.org`), `FINSEARCH_MODE` (default `normal`), `FINSEARCH_MODEL` override. All documented in `.env.example`.
- **Never auto-selected**: like OpenRouter, `resolve_integration()` only picks it when `integration: "finsearch"` is explicit.

Known contract asymmetries, accepted and documented in the module docstring:
- AF ignores `max_tokens`/`temperature` (not read by `/v1`); `LLM_MAX_OUTPUT_TOKENS` is a no-op for this provider.
- AF's `usage` is a char-count estimate (`len//4`), not a tokenizer — cost figures are approximate.
- AF requires `mode`; the shim supplies it (OpenAI clients don't send one).

Config + pricing:
- `dashboard/config/leaderboard.json` entry: `{"id": "agentic_finsearch", "name": "Agentic FinSearch", "label": "Model", "model": "FinSearch Trader", "provider": "SecureFinAI Lab", "strategy": "llm_agent", "integration": "finsearch", "model_id": "FinSearch-Trader", "mode": "safe_trading", "symbols": [], "auto_compute": false}`.
- `token_cost.py` `_PRICING_TABLE` row for `"FinSearch-Trader"` at the underlying foundation model's list price (exact numbers verified at impl time), so `est_cost_usd` approximates AF's real upstream spend rather than falling to the `(1.0, 5.0)` default.

## 6. The run — ops constraints (all verified against current code)

| Constraint | Value | Consequence |
|---|---|---|
| AF per-identity daily budget | `AGENT_DAILY_RUN_BUDGET = 100/day` per IP (`api/agent_budget.py:44-46`); **every** `/v1` call consumes a slot | 161 calls from one machine in one day **will be throttled at 100**. Ops task: raise the droplet env (e.g. `AGENT_DAILY_RUN_BUDGET=500`) for the run window, or accept a 2-day split. Budget raise is the recommendation — it's one env var, and the global 2000/day ceiling still protects the service. |
| AF gunicorn timeout | 120s/request | Direct path is a single foundation-model call (no tools) — typically seconds. Ample headroom. |
| ATL per-call resiliency | No retry on network/HTTP errors — first failure = rule-based fallback for that step (`portfolio_manager.py:468-471`) | H6 needs ≥95% of 161 steps model-driven → **≤8 failed steps total**. Direct-path reliability makes this realistic; the smoke test (below) is the gate. |
| H6 guard | `llm_decisions / decision_steps ≥ 0.95` (`service.py:39`) | The persona's format-compliance clause + ATL's tolerant JSON extraction (`_parse_llm_response` finds the first `{...}`) are the two layers that keep steps parseable. Never pass `--allow-fallback`. |
| Rate limit | 600/h per IP on AF | 161 calls spread over the run's wall-clock — no issue. |

**Run sequence** (identical to the six-LLM onboarding, per the recipe):
1. Smoke: `python3 dashboard/scripts/deploy_leaderboard_model.py --entry agentic_finsearch --start 2026-04-15 --end 2026-04-16` — catches auth/model-key/JSON issues for cents.
2. Full window: same command without dates (uses `leaderboard.json` window). Expect H6 to pass or fail loudly (exit 2).
3. Seed refresh: commit the regenerated `dashboard/storage/data/backtest.db` from an isolated worktree (`VACUUM INTO` snapshot; WAL mode — never commit with a live handle open), alongside the config/provider diffs.
4. Merge → CI deploys prod automatically (PR #95 deploy hook) → `GET /api/v1/leaderboard?refresh=true` → verify the entry renders.

## 7. Display

No frontend work. Verified: the leaderboard table, chart, legend, and detail panel key on generic fields (`team_name`, `model`, `is_model`, `entry_type`, `equity_curve`); the only name-keyed logic is a cosmetic style preset for 5 baseline labels; new labels auto-assign palette colors (`leaderboard.js:25-31,40-64`). "Agentic FinSearch" appears exactly like the other six models once the run row exists.

## 8. Future work (explicit, out of scope)

- **AF full-agentic benchmark** via `/api/v2` protocol runs in **live paper-trading** mode, where tools are legitimate — gated on Execution Phase B (`execution/paper_backend.py` is a stub today). This is where approach B comes back, and where Plan 1's signals (already in the v2 context envelope) meet Plan 3's agent.
- Feeding `news_sentiment` into the **internal** leaderboard prompt (`portfolio_manager.py` snapshot) — would change what *all* entries see; a deliberate new-contest-season decision, not a rider on this work.
- A `rationale`-aware trading log surface (the persona can say *why*; ATL persists `reasoning` per decision already).

## 9. Open questions flagged for Felix (non-blocking)

1. **Underlying model for `FinSearch-Trader`**: spec says AF's default family (`gemini-3-flash-preview`, provider `google`) — if the direct path's google client proves flaky at impl time, `openai`/`gpt-5.1-chat-latest` is the sanctioned fallback. Either is honest as "AF's configured brain."
2. **Cost display**: `est_cost_usd` will be an *approximation of AF's upstream spend* (char-estimate tokens × underlying list price). Alternative is displaying 0 (misleading) or omitting (inconsistent). Spec picks the approximation.
3. **Budget raise vs 2-day run split** for the 161-call window (spec recommends the env raise).
