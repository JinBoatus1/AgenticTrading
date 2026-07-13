# Discord → Backtest → Dashboard

Short note for the Discord demo path ([Issue #79](https://github.com/Open-Finance-Lab/AgenticTrading/issues/79)). Backend layering: [`dashboard-target-structure.md`](./dashboard-target-structure.md).

## Current workflow (user steps)

Full path that lands a run on a website agent card and opens it in Playground:

1. **Sign in** on the lab website and create at least one **built-in** agent (My Agents).
2. Click **Open Discord** (header or My Agents). First time: authorize Discord OAuth once so the site stores `users.discord_user_id`.
3. In the Discord bot channel, run **`/agent`** and pick one of your linked agents.
4. Optional: **`/ask`** to brainstorm rules, then **`/strategy`** to save a reusable prompt (or skip straight to backtest).
5. Run **`/backtest`** with either:
   - `prompt: …` (inline strategy text), or
   - `code: …` (saved strategy share code);
   optional `start:` / `end:` dates.
6. Wait for the bot reply: metrics summary + equity PNG. If an agent was selected, open the **Dashboard** deep link (`/app?view=backtest&agent_id=…&run_id=…`) to inspect the same run in Playground.

Shortcut (no account link / no agent card): skip steps 1–3 and run `/backtest prompt:…` alone — results stay on the Discord session only.

Operator cheat sheet: [`docs/discord-bot-instructions.md`](../discord-bot-instructions.md).

### What happens behind those steps

```text
User steps above
    │  /agent     →  GET /api/v1/discord/agents  (bot secret + Discord user id)
    │  /ask|/strategy → chat / strategy APIs
    │  /backtest  →  POST /backtest/run  (X-Session-Id)
    ▼
FastAPI (dashboard.backend.app)
    │  hourly engine + Alpaca bars + hosted LLM
    │  persist run (config, trades, equity, errors) in SQLite
    ▼
Discord: metrics + PNG + Dashboard deep link → Playground
```

| Piece | Role today |
| --- | --- |
| **Account link** | **Open Discord** → OAuth `identify` → `users.discord_user_id`. `/agent` lists that account’s agents only. |
| **Entrypoint** | `dashboard/backend/integrations/discord_bot.py` — HTTP client to the same API the website uses. |
| **Run** | `POST /backtest/run` + poll `GET /backtest/status`; builtin `agent_id` attaches the run to that agent’s card. |
| **Record** | Unique `run_id`; equity/metrics/plot via `/runs/...`. |
| **Hand-off** | Selected agent → Playground deep link in the bot reply. |

`/api/v1` is the compatibility surface the bot uses. New agent-facing work should prefer `/api/v2`; migrating Discord onto v2 is future work, not required for this demo.

## Future: paper trading from Discord

Paper trading already exists on the website (`/paper/*` → Alpaca paper via `domain/trading` + `infrastructure/brokers/alpaca_paper.py`). It is **not** wired into the Discord bot yet.

Intended direction (when Phase B lands):

1. Reuse the same account-link + agent selection path.
2. Drive live/paper steps through the v2 `ExecutionBackend` (`execution/paper_backend.py` is still a stub).
3. Keep Discord as a thin client: start/status/summary + a dashboard deep link into the paper session, same pattern as backtest — do not embed a second broker stack in the bot.

Until then, Discord remains **backtest-only**; paper stays on the web UI.
