# Agentic Trading Lab

Trading agents powered by LLMs: backtesting and paper trading with real Alpaca market data. Compare agent strategies against buy-and-hold and index baselines, with a web dashboard for equity curves and live quotes.

## Features

- **Real Alpaca data** — Hourly bars from the Alpaca API
- **Agent trading logic** — Technical indicators (RSI-14, MACD, Bollinger Bands, SMAs)
- **Backtest dashboard** — Three equity curves per run (agent, buy-and-hold, DJIA) from SQLite
- **Leaderboard view (mock MVP)** — Ten-team comparison UI with simulated curves
- **Paper trading API** — Live Alpaca paper account endpoints (`/paper/*`)
- **REST API** — Run metadata, equity curves, comparison, ticker
- **Web dashboard** — Chart.js, light/dark theme, session-aware backtests
- **Market ticker** — Stock quotes via Alpaca; crypto (e.g. BTC) via CoinGecko
- **Market hours only** — Trading restricted to 9:30 AM–4:00 PM ET
- **Session isolation** — Anonymous sessions for backtests (no auth required)
- **LLM validation** — Pydantic V2 schemas and tests in `backend/tests/` (example endpoint in `llm_integration_example.py`)

## Project Structure

```
AgenticTrading/
├── backend/              # FastAPI app, SQLite layer, paper trading, LLM validator
├── frontend/             # Dashboard (served by backend at http://localhost:8000)
├── scripts/              # CLI backtest (backtest_hourly_agent.py, etc.)
├── config/               # Default run IDs and date range (defaults.json)
├── data/                 # SQLite backtest results (backtest.db)
├── credentials/          # Local only — not in git (see alpaca.json.example)
├── backups/              # Database backups
└── orchestration/        # FinAgent multi-agent framework (separate subsystem)
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Backtest Engine (scripts/backtest_hourly_agent.py)          │
│ ├─ Fetch Alpaca hourly bars                                 │
│ ├─ Run agent + baseline logic                               │
│ ├─ Write 3 runs (agent, buy-and-hold, DJIA)                 │
│ └─ Store in data/backtest.db (SQLite)                        │
└────────────────┬────────────────────────────────────────────┘
                 │
┌────────────────▼─────────────────────────────────────────────┐
│ REST API (backend/app.py)                                    │
│ ├─ GET  /health                                              │
│ ├─ GET  /runs, /runs/{id}/equity, /compare                   │
│ ├─ POST /backtest/run, GET /backtest/status                  │
│ ├─ GET  /ticker                                              │
│ ├─ GET  /paper/account, /paper/positions, …                  │
│ └─ GET  /config/defaults                                     │
│     (LLM example: backend/llm_integration_example.py only)   │
└────────────────┬────────────────────────────────────────────┘
                 │
┌────────────────▼─────────────────────────────────────────────┐
│ Web Dashboard (frontend/)                                    │
│ ├─ index.html, app.js, styles.css                            │
│ └─ images/                                                   │
└──────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Alpaca credentials

Use **either** environment variables **or** a local credentials file.

**Option A — `.env` (recommended for deploy):**

```bash
cp .env.example .env
# Edit .env:
# ALPACA_API_KEY=your_key
# ALPACA_SECRET_KEY=your_secret
# ALPACA_BASE_URL=https://paper-api.alpaca.markets
```

**Option B — local file (for backtest CLI and local API fallback):**

```bash
cp credentials/alpaca.json.example credentials/alpaca.json
# Edit credentials/alpaca.json with your paper-trading keys
```

The `credentials/` folder is not tracked in git. See `credentials/README.md`.

### 3. Start API server

```bash
python3 backend/app.py
```

### 4. Open dashboard

```
http://localhost:8000/
```

### 5. Run a backtest (optional)

Requires valid Alpaca credentials (`.env` or `credentials/alpaca.json`):

```bash
python3 scripts/backtest_hourly_agent.py --start 2026-03-01 --end 2026-03-31
```

Or trigger via API after starting the server: `POST /backtest/run`.

**Agent modes** (CLI flag on `backtest_hourly_agent.py`):

```bash
python3 scripts/backtest_hourly_agent.py --mode safe_trading   # default — active strategy with indicators
python3 scripts/backtest_hourly_agent.py --mode buy_and_hold   # validation — buy once, then hold
```

## Key Features

### Backtest mode (SQLite-backed)

- Three curves: agent, buy-and-hold, DJIA
- Session-scoped runs via `X-Session-Id` / middleware
- Continuous trading-hour index on charts (no overnight line gaps)
- Market-hours filter on equity points (9:30 AM–4:00 PM ET, `pytz`)

### Leaderboard mode (mock UI)

- Ten-team table and charts with **simulated** performance (frontend only)
- Future work: wire to real multi-agent runs

### Paper trading

- Endpoints under `/paper/*` read live Alpaca paper account data when credentials are configured
- Baselines for paper comparison: `/paper/baselines`

### LLM security and validation

- **Pydantic V2** — `backend/llm_validator.py`
- **Tests** — `backend/tests/` (validator, isolation, endpoint integration)
- **Example API** — `POST /api/llm-trading-decision` in `backend/llm_integration_example.py` (not mounted on the main `app.py` server)

Run the example:

```bash
python3 backend/llm_integration_example.py
```

## Database Schema

SQLite database path: `data/backtest.db` (override with `DATABASE_PATH`).

### `agent_runs`

```sql
run_id (PK), session_id, agent_name, mode, start_date, end_date,
initial_equity, final_equity, total_return, sharpe_ratio, max_drawdown,
num_trades, llm_model, created_at, updated_at
```

### `equity_timeseries`

```sql
id (PK), run_id (FK), timestamp, equity, cash, positions_value, daily_return
```

### `trades`

```sql
id (PK), run_id (FK), timestamp, symbol, quantity, side, price, value, reason
```

**Modes in use:**

- `backtest` — Historical runs stored in SQLite
- `paper` — Live paper-trading sessions (when Alpaca is configured)

## Development

### Technology stack

- **Backend:** FastAPI 0.135.3, SQLite, Uvicorn
- **Frontend:** HTML5, Chart.js, vanilla JavaScript
- **Broker:** Alpaca Trade API (paper)
- **Python:** 3.13 (`.python-version`; Render uses `backend/runtime.txt`)

### Testing

```bash
pip install pytest   # not pinned in requirements.txt

# All backend tests
pytest backend/tests -v

# Manual smoke test
python3 backend/app.py
# Open http://localhost:8000
```

## Deployment

### Local development

See **Quick Start** above.

### Docker (partial)

The current `Dockerfile` copies `backend/` only. For a full local dashboard you also need `frontend/` and `data/` on the image or mounted volumes. Example (run from repo root):

```bash
docker build -t agentic-trading .
docker run -p 8000:8000 \
  -e ALPACA_API_KEY=your_key \
  -e ALPACA_SECRET_KEY=your_secret \
  -v "$(pwd)/data:/app/data" \
  -v "$(pwd)/frontend:/app/frontend" \
  agentic-trading
```

### Render.com

- `render.yaml` — `rootDir: backend/`, persistent disk for DB
- Set `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` in the service environment

### Vercel (static frontend only)

`vercel.json` serves static files from the project root. It does **not** run the FastAPI backend. Point the frontend at your API host (e.g. Render) if you split frontend and API.

## Future Roadmap

- [ ] Leaderboard backed by real multi-agent runs (replace mock data)
- [ ] Sentiment analysis (Reddit, news APIs)
- [ ] Monte Carlo simulation baselines
- [ ] Production-ready Docker image (frontend + data included)

## FinAgent Orchestration Framework

This repo also includes the **FinAgent Orchestration Framework** under `orchestration/`. See `orchestration/README.md` for multi-agent architecture, memory systems, and DAG-based planning.

## License

MIT — See [LICENSE](LICENSE)

## Contributing

Pull requests and issues welcome!

---

Built with Alpaca API, FastAPI, Chart.js, and SQLite
