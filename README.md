# Agentic Trading Lab

Trading agents powered by LLMs backtesting and paper trading platform with real Alpaca market data. Compare LLM trading agents (DeepSeek, Claude, GPT) on the same market stream and benchmark performance against buy-and-hold and index baselines.

## Features

✅ **Real Alpaca Data Integration** - Hourly bars from official Alpaca API  
✅ **Agent Trading Logic** - Technical indicators (RSI-14, MACD, Bollinger Bands, SMAs)  
✅ **Leaderboard & Equity Curves** - Multi-agent performance dashboard with interactive charts  
✅ **3 Equity Curves per Backtest** - Agent performance vs buy-and-hold baseline vs DJIA index  
✅ **Backtesting Engine** - 30+ days of historical data with full trade logging  
✅ **REST API** - Serve equity data to frontend dashboard  
✅ **Web Dashboard** - Chart.js visualization with light/dark theme  
✅ **Market Ticker** - Live prices from Alpaca + CoinGecko  
✅ **Market Hours Only** - Trading restricted to 9:30 AM - 4:00 PM ET  
✅ **Session Isolation** - Anonymous session support for backtesting (no auth required)  
✅ **LLM Security** - Validated LLM responses with Pydantic V2 (38+ tests)  

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Backtest Engine (scripts/backtest_hourly_agent.py)          │
│ ├─ Fetch real Alpaca hourly bars                           │
│ ├─ Run agent trading logic (120+ trades)                   │
│ ├─ Generate 3 equity curves                                │
│ └─ Store in SQLite database                                │
└────────────────┬────────────────────────────────────────────┘
                 │
┌────────────────▼─────────────────────────────────────────────┐
│ REST API (backend/app.py)                                    │
│ ├─ GET /runs - List all runs                               │
│ ├─ GET /runs/{run_id}/equity - Equity curve                │
│ ├─ GET /compare - Compare multiple runs                    │
│ ├─ GET /ticker - Live market quotes                        │
│ └─ POST /llm-trading-decision - Validated LLM decisions    │
└────────────────┬────────────────────────────────────────────┘
                 │
┌────────────────▼─────────────────────────────────────────────┐
│ Web Dashboard (frontend/)                                    │
│ ├─ index.html - Page layout                                │
│ ├─ app.js - Chart.js + API calls + session mgmt            │
│ ├─ styles.css - Light/dark theme styling                   │
│ └─ images/ - New ATL logo (cyan + arrows)                  │
└──────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Alpaca Credentials
```bash
# Create .env file
cp .env.example .env

# Edit .env with your credentials:
# ALPACA_API_KEY=YOUR_API_KEY
# ALPACA_SECRET_KEY=YOUR_SECRET_KEY
# ALPACA_BASE_URL=https://paper-api.alpaca.markets
```

### 3. Run Backtest
```bash
python3 scripts/backtest_hourly_agent.py --start 2026-03-01 --end 2026-03-31
```

### 4. Start API Server
```bash
python3 backend/app.py
# Server runs at http://localhost:8000
```

### 5. Open Dashboard
```
http://localhost:8000/
```

## Key Features

### Leaderboard & Equity Curves
- **Interactive multi-agent dashboard** with Chart.js
- **10-team leaderboard** (7 competing agents + 3 baselines)
- **Dual-view** - Toggle between % return and $ value
- **Responsive design** - Works on mobile (single-column) and desktop (two-column)
- **All teams start at $100k** - Perfect visual alignment
- **44-day timeline** - Sep 1 - Oct 30 trading period

### Session Isolation
- **Anonymous sessions** - No authentication required for backtesting
- **Unique session_id** stored in localStorage
- **URL sharing** - TensorFlow Playground-style shareable URLs with config parameters
- **Separate queries** - Session B cannot access Session A's backtests

### Continuous Trading Hour Index
- X-axis uses sequential indices (0, 1, 2...) instead of timestamps
- Eliminates visual "overnight gap" artifacts (no lines connecting 4 PM to 9:30 AM)
- Date labels show market dates ("Mar 01", "Mar 02")
- Hover tooltips display actual timestamps

### Market Hours Filter
- Trading only occurs 9:30 AM - 4:00 PM ET
- Backend filters all equity data to market hours
- Timezone-aware using pytz

### Baseline Architecture
- Reusable `BaselineGenerator` class for consistent baseline generation
- Buy-and-Hold: Equal-weighted equity held for full period
- DJIA Index: Market-context baseline
- Both use same real data as agent

### LLM Security & Validation
- **Pydantic V2 schema validation** - Strict response format enforcement
- **Tool rejection** - Detects and rejects LLM tool-calling attempts
- **Portfolio constraints** - Validates position sizing and cash reserves
- **38+ security tests** - Comprehensive coverage (unit + integration)
- **Audit trail** - All decisions logged for compliance
- **No tool exposure** - LLM receives only sanitized market snapshots

## Database Schema

### `runs` table
```sql
run_id (PK), session_id (FK), agent_name, mode, initial_equity, final_equity,
total_return, sharpe_ratio, max_drawdown, created_at
```

### `equity_data` table
```sql
run_id (FK), timestamp, equity, cash, positions_value, daily_return
```

**Modes:**
- `backtest` - test agent performance on historical data
- `paper` - Live trading in alpaca paper trading account
- `leaderboard` - submit and compete your agent with others!

## Performance Metrics

**Recent 44-Day Backtest (Sep 1 - Oct 30, 2026)**
- Best agent: +12.47% return
- Worst agent: -3.12% return
- Buy-and-Hold baseline: Tracked market performance
- DJIA baseline: Index reference

All teams start at $100,000 initial equity.

## Future Roadmap

- [ ] Live paper trading service with Alpaca integration
- [ ] Sentiment analysis integration (Reddit, news APIs)
- [ ] Monte Carlo simulation baselines

## Development

### Technology Stack
- **Backend:** FastAPI 0.135.3, SQLite
- **Frontend:** HTML5, Chart.js, Vanilla JavaScript
- **Broker:** Alpaca Trade API (paper trading)
- **Python:** 3.13 (pinned in .python-version)
- **Validation:** Pydantic V2 with @field_validator

### Version Control
This repo uses continuous deployment:
- Each backtest/feature gets a commit
- `main` branch is always deployable
- Use `git checkout HEAD~1` to revert if needed

### Testing
```bash
# Manual dashboard test
python3 backend/app.py
# Open http://localhost:8000 and verify charts render

# Run security tests
pytest backend/tests/test_llm_validator.py -v

# Database audit
sqlite3 data/backtest.db "SELECT agent_name, total_return FROM runs LIMIT 5;"
```

## Deployment

### Local Development
See **Quick Start** above for running locally.

### Docker
```bash
docker build -t agentic-trading .
docker run -p 8000:8000 \
  -e ALPACA_API_KEY=*** \
  -e ALPACA_SECRET_KEY=*** \
  -v $(pwd)/data:/data \
  agentic-trading
```

### Render.com
- Python version: `3.13` (pinned in `.python-version`)
- rootDir: `backend/`
- See `render.yaml` for deployment config

### Vercel (Frontend)
- See `vercel.json` for deployment config
- Frontend assets served from `frontend/` directory

## FinAgent Orchestration Framework

This repo also contains the **FinAgent Orchestration Framework** for multi-agent trading systems. See `orchestration/README.md` for details on:
- Multi-agent architecture
- Protocol-oriented agent coordination
- Memory-augmented agent systems
- DAG-based task planning

## License

MIT - See LICENSE file

## Contributing

This is a personal trading lab. Pull requests and issues welcome!

---

Built with ❤️ using Alpaca API, FastAPI, Chart.js, and SQLite
