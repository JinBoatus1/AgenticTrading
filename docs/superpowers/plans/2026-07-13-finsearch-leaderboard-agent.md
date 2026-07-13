# Agentic FinSearch as a Leaderboard Trading Agent — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put Agentic FinSearch on the leaderboard exactly like the other model entries — AF-side professional-trader persona (direct, tools-off path), ATL-side `finsearch` provider shim, config entry, pricing, then the contest run + seed refresh.

**Architecture:** Task 1 lands in the **Agentic-FinSearch repo** (persona + config-driven direct path, generalizing the existing buffet branch). Tasks 2–5 land in **ATL** (provider module following the PR #96 OpenRouter pattern, leaderboard.json entry, pricing row, env docs). Task 6 is the run itself (smoke → full window → seed-DB commit) — the same recipe the six existing LLM entries used.

**Tech Stack:** Django + OpenAI-compatible view (AF), `requests` shim returning Anthropic-shaped objects (ATL), `deploy_leaderboard_model.py` (run), SQLite seed DB commit.

**Spec:** `docs/superpowers/specs/2026-07-13-finsearch-leaderboard-agent-design.md`.

## Global Constraints

- **No look-ahead:** the leaderboard entry must only ever call AF's direct, tools-off path (`FinSearch-Trader`). Never point `FINSEARCH_MODE`/model at a tool-attached mode for a backtest run.
- **Never pass `--allow-fallback`** to the deploy script — H6 exists to stop exactly that.
- ATL provider contract (from `providers/__init__.py:1-13`): module exposes `INTEGRATION_ID`, `DEFAULT_MODEL`, `default_model_name()`, `make_client(anthropic_cls)`; `make_client` returns `None` on missing key (printed warning, never raises); registered in `PROVIDERS`; never auto-selected.
- Seed-DB commits: regenerate via the deploy script, snapshot with `VACUUM INTO` from an isolated git worktree (WAL mode), commit the binary + config diffs together. Always set `DATABASE_PATH` when smoke-testing so the committed seed stays clean.
- AF repo tests run via `cd Main/backend && uv run pytest`; ATL tests via `pytest dashboard/backend/tests/ -v` from the repo root.
- `CommonStack` hijack gotcha: `resolve_integration()` prefers CommonStack when `COMMONSTACK_API_KEY` is set and no integration is explicit — the leaderboard entry sets `"integration": "finsearch"` explicitly, so this cannot bite; do not remove that field.

---

### Task 1 (Agentic-FinSearch repo): trader persona + config-driven direct path

**Repo:** `/mnt/d/FinGPT/Github/fingpt_rcos` — own branch + PR there (reference this plan in the PR body).

**Files:**
- Modify: `Main/backend/datascraper/datascraper.py` (persona registry near `BUFFETT_INSTRUCTION` at `:101-111`; direct-path branch at `:1015-1021`; instruction selection in `_prepare_messages` at `:281-291`)
- Modify: `Main/backend/datascraper/models_config.py:6-40` (new `FinSearch-Trader` entry; add `"direct": True, "persona": "buffett"` to `Buffet-Agent`)
- Test: `Main/backend/tests/test_trader_persona.py` (new; mirror the buffet cases in `tests/test_openai_api.py`)

**Interfaces:**
- Produces: `MODELS_CONFIG["FinSearch-Trader"]` reachable via `POST /v1/chat/completions {"model": "FinSearch-Trader", "mode": "normal", ...}`; response is standard OpenAI shape (no tools ever invoked); `TRADER_INSTRUCTION` and `PERSONA_INSTRUCTIONS` constants.

- [ ] **Step 1: Write the failing tests**

```python
# Main/backend/tests/test_trader_persona.py
from datascraper.models_config import MODELS_CONFIG
from datascraper import datascraper as ds


def test_finsearch_trader_registered():
    cfg = MODELS_CONFIG["FinSearch-Trader"]
    assert cfg["direct"] is True
    assert cfg["persona"] == "trader"


def test_persona_registry_selects_trader():
    assert ds.PERSONA_INSTRUCTIONS["trader"] is ds.TRADER_INSTRUCTION
    assert ds.PERSONA_INSTRUCTIONS["buffett"] is ds.BUFFETT_INSTRUCTION


def test_prepare_messages_uses_trader_instruction():
    # real signature: _prepare_messages(message_list, user_input, model=None)
    # -> (msgs, system_message)   (datascraper.py:245-297)
    msgs, _system = ds._prepare_messages([], "What do you do?",
                                         model="FinSearch-Trader")
    joined = " ".join(m.get("content", "") for m in msgs)
    assert "FinSearch Trader" in joined          # persona applied
    assert "Warren Buffett" not in joined


def test_buffet_still_uses_buffett_instruction():
    msgs, _system = ds._prepare_messages([], "hi", model="Buffet-Agent")
    joined = " ".join(m.get("content", "") for m in msgs)
    assert "Warren Buffett" in joined
```

- [ ] **Step 2: Run to verify failure** — `cd Main/backend && uv run pytest tests/test_trader_persona.py -v` → FAIL (`KeyError: 'FinSearch-Trader'`).

- [ ] **Step 3: Implement**

```python
# datascraper.py — beside BUFFETT_INSTRUCTION
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

PERSONA_INSTRUCTIONS = {
    "buffett": BUFFETT_INSTRUCTION,
    "trader": TRADER_INSTRUCTION,
}
```

- In `_prepare_messages` (`:281-291`, the exact current selection is
  `instruction = INSTRUCTION`; `if model:` → `get_model_config(model)` → `if model_config and model_config.get("provider") == "buffet": instruction = BUFFETT_INSTRUCTION`):
  replace the provider check with
  `instruction = PERSONA_INSTRUCTIONS.get(model_config.get("persona"), INSTRUCTION) if model_config else INSTRUCTION`
  and generalize the log line (`logging.info("[PERSONA] Using %s system prompt", persona)`).
- In `create_agent_response` (`:1015-1021`): replace `provider == "buffet"` with
  `model_config.get("direct") or provider == "buffet"` (belt-and-suspenders; config now carries `direct: True` for buffet too).
- `models_config.py`: add the `FinSearch-Trader` entry exactly as in spec §4.1 (provider `google` / `gemini-3-flash-preview`; **verify at impl time that the direct path's google client works — if flaky, the sanctioned fallback is provider `openai` / `gpt-5.1-chat-latest`**), and add `"direct": True, "persona": "buffett"` to `Buffet-Agent`.

- [ ] **Step 4: Run the new tests + the existing OpenAI-API suite**

Run: `cd Main/backend && uv run pytest tests/test_trader_persona.py tests/test_openai_api.py -v`
Expected: PASS (buffet behavior unchanged; `/v1/models` test may need its expected-count updated — that update belongs in this task).

- [ ] **Step 5: One manual live check** (needs env keys): `curl -s -X POST http://localhost:8000/v1/chat/completions -H "Content-Type: application/json" -d '{"model":"FinSearch-Trader","mode":"normal","messages":[{"role":"user","content":"Reply with exactly the JSON {\"ok\": true} and nothing else."}]}'` → `choices[0].message.content` is exactly `{"ok": true}` (format-compliance clause working).

- [ ] **Step 6: Docs + commit + PR.** Add the model row to `Docs/source/api_reference.rst`'s model table. Commit, push branch `feat/trader-persona`, open PR against the repo's current working convention (recent precedent: PRs to `main`), body references this plan. Review before merging (loop protocol).

---

### Task 2 (ATL): `finsearch` provider module

**Files:**
- Create: `dashboard/backend/infrastructure/llm/providers/finsearch.py`
- Modify: `dashboard/backend/infrastructure/llm/providers/__init__.py:31-35` (register in `PROVIDERS`)
- Test: `dashboard/backend/tests/llm/test_providers.py` (extend — the provider-contract cases added by PR #96 are the template)

**Interfaces:**
- Consumes: nothing from other tasks (independent of Task 1 until the run).
- Produces: `INTEGRATION_ID = "finsearch"`; `make_client(anthropic_cls) -> FinSearchClient | None`; `FinSearchClient.messages.create(model, max_tokens, messages, system=None, **kw)` returning an object with `.content` (list of one `type="text"` block) and `.usage.input_tokens/.output_tokens`.

- [ ] **Step 1: Write the failing tests**

```python
# append to dashboard/backend/tests/llm/test_providers.py
from types import SimpleNamespace

from dashboard.backend.infrastructure.llm.providers import (PROVIDERS,
                                                            resolve_integration)
from dashboard.backend.infrastructure.llm.providers import finsearch


def test_finsearch_registered():
    assert PROVIDERS["finsearch"] is finsearch
    assert finsearch.DEFAULT_MODEL == "FinSearch-Trader"
    assert finsearch.default_model_name() == "FinSearch-Trader"


def test_finsearch_never_auto_selected(monkeypatch):
    monkeypatch.delenv("COMMONSTACK_API_KEY", raising=False)
    assert resolve_integration(None) != "finsearch"


def test_finsearch_client_none_without_key(monkeypatch, capsys):
    monkeypatch.delenv("FINGPT_API_KEY", raising=False)
    assert finsearch.make_client(object) is None
    assert "FINGPT_API_KEY" in capsys.readouterr().out


def test_finsearch_messages_create_shapes_anthropic_response(monkeypatch):
    monkeypatch.setenv("FINGPT_API_KEY", "k")
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured.update(url=url, json=json, headers=headers, timeout=timeout)
        return SimpleNamespace(
            status_code=200,
            raise_for_status=lambda: None,
            json=lambda: {
                "choices": [{"message": {"role": "assistant",
                                         "content": '{"actions": []}'},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 8,
                          "total_tokens": 108},
            },
        )

    monkeypatch.setattr(finsearch, "_post", fake_post)
    client = finsearch.make_client(object)
    resp = client.messages.create(
        model="FinSearch-Trader", max_tokens=2000,
        messages=[{"role": "user", "content": "prompt"}], system="sys",
    )
    assert captured["json"]["model"] == "FinSearch-Trader"
    assert captured["json"]["mode"] == "normal"
    assert captured["json"]["messages"][0] == {"role": "system", "content": "sys"}
    assert captured["headers"]["Authorization"] == "Bearer k"
    assert resp.content[0].type == "text"
    assert resp.content[0].text == '{"actions": []}'
    assert resp.usage.input_tokens == 100 and resp.usage.output_tokens == 8
```

- [ ] **Step 2: Run to verify failure** — `pytest dashboard/backend/tests/llm/test_providers.py -v -k finsearch` → FAIL (import error).

- [ ] **Step 3: Implement**

```python
# dashboard/backend/infrastructure/llm/providers/finsearch.py
"""Agentic FinSearch gateway — Anthropic-shaped shim over AF's OpenAI-compatible /v1.

Contract asymmetries (accepted): AF ignores max_tokens/temperature (LLM_MAX_OUTPUT_TOKENS
is a no-op here); AF's usage tokens are char-count estimates (len//4), so costs are
approximate; AF requires a `mode` field — the shim supplies FINSEARCH_MODE (default
"normal"). Leaderboard runs must target the direct, tools-off FinSearch-Trader model:
tool-attached modes would look ahead in a backtest.
"""
from __future__ import annotations

import os
from types import SimpleNamespace

import requests

INTEGRATION_ID = "finsearch"
DEFAULT_MODEL = "FinSearch-Trader"
DEFAULT_BASE_URL = "https://agenticfinsearch.org"
_TIMEOUT_SECONDS = 150  # AF's gunicorn kills at 120s; margin classifies failures client-side


def default_model_name() -> str:
    return os.environ.get("FINSEARCH_MODEL", DEFAULT_MODEL)


def _post(url, json=None, headers=None, timeout=None):
    return requests.post(url, json=json, headers=headers, timeout=timeout)


class _FinSearchMessages:
    def create(self, *, model, max_tokens=None, messages=None, system=None, **_):
        url = os.environ.get("FINSEARCH_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
        payload_messages = list(messages or [])
        if system:
            payload_messages.insert(0, {"role": "system", "content": system})
        resp = _post(
            f"{url}/v1/chat/completions",
            json={
                "model": model or default_model_name(),
                "mode": os.environ.get("FINSEARCH_MODE", "normal"),
                "messages": payload_messages,
            },
            headers={"Authorization": f"Bearer {os.environ['FINGPT_API_KEY']}"},
            timeout=_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        body = resp.json()
        text = body["choices"][0]["message"]["content"]
        usage = body.get("usage") or {}
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=text)],
            usage=SimpleNamespace(
                input_tokens=int(usage.get("prompt_tokens", 0)),
                output_tokens=int(usage.get("completion_tokens", 0)),
            ),
        )


class FinSearchClient:
    def __init__(self):
        self.messages = _FinSearchMessages()


def make_client(anthropic_cls):
    if not os.environ.get("FINGPT_API_KEY"):
        print("[finsearch] FINGPT_API_KEY not set — finsearch integration unavailable")
        return None
    return FinSearchClient()
```

Register in `providers/__init__.py` `PROVIDERS` dict (import the module, add `finsearch.INTEGRATION_ID: finsearch`).

- [ ] **Step 4: Run** — `pytest dashboard/backend/tests/llm/test_providers.py -v` → PASS (including the pre-existing provider-contract sweep, which iterates `PROVIDERS` — the new module must satisfy it).

- [ ] **Step 5: Commit** — `git commit -m "feat(llm): finsearch provider — Anthropic shim over AF /v1 (tools-off trader model)"`.

---

### Task 3 (ATL): pricing row

**Files:**
- Modify: `dashboard/backend/infrastructure/llm/token_cost.py:27-58` (`_PRICING_TABLE`)
- Test: `dashboard/backend/tests/llm/` (wherever token-cost cases live — Grep `estimate_cost_usd` under tests)

- [ ] **Step 1: Failing test** — `estimate_cost_usd("FinSearch-Trader", 1_000_000, 1_000_000)` equals the underlying model's list price sum, not the `(1.0, 5.0)` default.

```python
def test_finsearch_trader_priced():
    from dashboard.backend.infrastructure.llm.token_cost import estimate_cost_usd
    cost = estimate_cost_usd("FinSearch-Trader", 1_000_000, 1_000_000)
    assert cost != 6.0  # not the default (1.0 + 5.0) — a real row must match first
```

- [ ] **Step 2: Add the row** — `("FinSearch-Trader", <in>, <out>)` at the underlying foundation model's **current list price** (verify gemini-3-flash-preview's published rate at impl time; if Task 1 fell back to `gpt-5.1-chat-latest`, use that model's rate). Comment the row with the upstream model + verification date.
- [ ] **Step 3: Run + commit** — `pytest dashboard/backend/tests/llm/ -v` → PASS; `git commit -m "feat(llm): FinSearch-Trader pricing row (approx upstream spend)"`.

---

### Task 4 (ATL): leaderboard entry + env docs

**Files:**
- Modify: `dashboard/config/leaderboard.json` (append to `strategies` after the Nemotron entry at `:127-139`)
- Modify: `.env.example` (add `FINSEARCH_BASE_URL=`, `FINSEARCH_MODE=normal`, `FINSEARCH_MODEL=` beside the OpenRouter block; `FINGPT_API_KEY` is added by Plan 1's Task 7 — if that hasn't merged yet, add it here)

- [ ] **Step 1: Add the entry**

```json
{
  "id": "agentic_finsearch",
  "name": "Agentic FinSearch",
  "label": "Model",
  "model": "FinSearch Trader",
  "provider": "SecureFinAI Lab",
  "strategy": "llm_agent",
  "integration": "finsearch",
  "model_id": "FinSearch-Trader",
  "mode": "safe_trading",
  "symbols": [],
  "auto_compute": false
}
```

- [ ] **Step 2: Sanity test** — `python3 dashboard/scripts/deploy_leaderboard_model.py --list` shows the entry with integration `finsearch`; `pytest dashboard/backend/tests/domain/leaderboard/ -v` → PASS (config-shape guards).
- [ ] **Step 3: Commit** — `git commit -m "feat(leaderboard): Agentic FinSearch entry (finsearch integration, manual deploy)"`.

---

### Task 5 (ops): environment for the run

Manual checklist (no code):

- [ ] AF droplet: raise `AGENT_DAILY_RUN_BUDGET` to `500` for the run window (env for the `fingpt-api` unit; the deploy-owned env file — same place `FINGPT_API_KEY`/`REQUIRE_FINGPT_API_KEY` live). Revert after the run if desired.
- [ ] Local ATL `dashboard/.env`: `FINGPT_API_KEY=<the FinSearch backend key>`; optionally `FINSEARCH_BASE_URL` if targeting staging.
- [ ] Confirm AF prod is serving `FinSearch-Trader` (Task 1 merged + deployed): the Step-5 curl from Task 1, against `https://agenticfinsearch.org`.

---

### Task 6: smoke run → full run → seed refresh

- [ ] **Step 1: Smoke (1 trading day, costs cents)**

```bash
DATABASE_PATH=/tmp/atl-smoke.db python3 dashboard/scripts/deploy_leaderboard_model.py \
  --entry agentic_finsearch --start 2026-04-15 --end 2026-04-16
```

Expected: exits 0; printed coverage 100% (or ≥95%); no `LeaderboardFallbackError`. If it exits 2, diagnose (auth? model key? JSON compliance?) — do NOT proceed to the full window.

- [ ] **Step 2: Full contest window** (161 steps; direct path ≈ seconds/call → well under an hour)

```bash
python3 dashboard/scripts/deploy_leaderboard_model.py --entry agentic_finsearch
```

Expected: exits 0, H6 passes, run row written to `dashboard/storage/data/backtest.db`.

- [ ] **Step 3: Seed refresh commit** (worktree + VACUUM INTO pattern)

```bash
sqlite3 dashboard/storage/data/backtest.db "VACUUM INTO '/tmp/backtest-snapshot.db'"
git worktree add /tmp/atl-seed-refresh main
cp /tmp/backtest-snapshot.db /tmp/atl-seed-refresh/dashboard/storage/data/backtest.db
# commit there alongside the leaderboard.json/provider diffs if not already merged
```

- [ ] **Step 4: Verify display** — locally: `uvicorn dashboard.backend.app:app` → `/app` → Competition → Leaderboard shows "Agentic FinSearch" with curve, return, Sharpe (zero frontend edits). After merge: prod auto-deploys (PR #95 hook) → `GET /api/v1/leaderboard?refresh=true` → verify live.
- [ ] **Step 5: `/code-review` + merge** per the loop protocol.

---

## Verification (whole plan)

1. AF: `uv run pytest` green including new persona tests; live curl proves format compliance.
2. ATL: `pytest dashboard/backend/tests/ -v` fully green.
3. H6 guard passes on the real full-window run — **the** acceptance gate.
4. Leaderboard page renders the entry with no frontend diff (`git diff --stat` shows none under `dashboard/frontend/`).
5. Both repos' PRs self-reviewed before merge.
