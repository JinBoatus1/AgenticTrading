# Agentic Trading Dashboard - Backtesting Architecture (v1)

## Design Goals
- **Minimal** — Only what's needed for milestone 1
- **Extensible** — Easy to add paper trading, leaderboards, trade logs later
- **Real-time friendly** — Same database structure works for live + backtest
- **Separated concerns** — Backtest logic, storage, API, UI are independent

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│  BACKTEST SCRIPT                                            │
│  backtest_orchestrator.py                                   │
│  • Loop through agent configs                               │
│  • Call orchestrator.run_pipeline(symbols, dates)           │
│  • Receive equity time-series from each agent               │
│  • Write to SQLite with run_id                              │
└──────────────────────┬──────────────────────────────────────┘
                       │ (agent, timestamp, equity)
                       ↓
┌─────────────────────────────────────────────────────────────┐
│  SQLite DATABASE (shared, versioned)                        │
│  backtest.db                                                │
│                                                              │
│  Tables:                                                    │
│  • agent_runs      [run_id, agent_name, mode, metrics]     │
│  • equity_timeseries [run_id, timestamp, equity, cash]     │
│  • trades          [run_id, timestamp, symbol, qty, price] │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ↓
┌─────────────────────────────────────────────────────────────┐
│  BACKEND API (FastAPI/Flask)                                │
│  backend/app.py                                             │
│                                                              │
│  Routes:                                                    │
│  • GET /runs                      (list all runs)           │
│  • GET /runs/{run_id}/equity      (equity curve for run)    │
│  • GET /compare?run_ids=...       (multi-run comparison)    │
│  • GET /runs/{run_id}/metrics     (Sharpe, return, etc.)    │
└──────────────────────┬──────────────────────────────────────┘
                       │ (JSON)
                       ↓
┌─────────────────────────────────────────────────────────────┐
│  FRONTEND DASHBOARD (HTML + Chart.js)                       │
│  frontend/index.html + app.js                               │
│                                                              │
│  Interface:                                                 │
│  • Run selector (multi-select)                              │
│  • Multi-line equity chart                                  │
│  • Summary metrics cards                                    │
│  • (Later: leaderboard, trades log, signals)                │
└─────────────────────────────────────────────────────────────┘
```

---

## Database Schema (SQLite)

### Table 1: `agent_runs` (metadata)
Stores one row per backtest execution.

```sql
CREATE TABLE agent_runs (
    run_id TEXT PRIMARY KEY,
    agent_name TEXT NOT NULL,
    mode TEXT NOT NULL,  -- 'backtest' or 'paper'
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    initial_equity REAL NOT NULL,
    final_equity REAL,
    total_return REAL,
    sharpe_ratio REAL,
    max_drawdown REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Example:**
```
run_id='alpha_20260410_v1'
agent_name='Alpha Agent'
mode='backtest'
start_date='2024-01-01'
end_date='2025-12-31'
initial_equity=100000
final_equity=120500
total_return=0.205
sharpe_ratio=1.2
max_drawdown=-0.15
```

### Table 2: `equity_timeseries` (time-series data)
Daily snapshots of equity for each agent.

```sql
CREATE TABLE equity_timeseries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,  -- ISO 8601 date or datetime
    equity REAL NOT NULL,
    cash REAL NOT NULL,
    positions_value REAL NOT NULL,
    daily_return REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES agent_runs(run_id),
    UNIQUE(run_id, timestamp)
);

CREATE INDEX idx_run_timestamp ON equity_timeseries(run_id, timestamp);
```

**Example:**
```
run_id='alpha_20260410_v1'
timestamp='2024-01-02'
equity=100500
cash=45000
positions_value=55500
daily_return=0.005
```

### Table 3: `trades` (optional, for later)
```sql
CREATE TABLE trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    symbol TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    side TEXT NOT NULL,  -- 'buy' or 'sell'
    price REAL NOT NULL,
    value REAL NOT NULL,
    reason TEXT,  -- 'signal_trigger', 'risk_adjustment', etc.
    FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
);
```

---

## File Structure

```
workspace/
├── BACKTEST_ARCHITECTURE.md          ← You are here
│
├── scripts/
│   └── backtest_orchestrator.py      # 1. Run backtests & write to DB
│
├── backend/
│   ├── app.py                        # 2. FastAPI server
│   ├── database.py                   # SQLite helpers
│   ├── models.py                     # Pydantic response models
│   └── requirements.txt
│
├── frontend/
│   ├── index.html                    # 3. Dashboard HTML
│   ├── app.js                        # Chart.js + fetch logic
│   └── styles.css
│
├── data/
│   └── backtest.db                   # SQLite database (gitignored)
│
└── README.md
```

---

## Data Flow (Backtest Mode)

### 1. Backtester Runs
```
backtest_orchestrator.py:
  run_id = generate_id()  # e.g., "alpha_20260410_v1"
  
  for agent in agents:
    result = orchestrator.run_pipeline(
      symbols=['AAPL', 'MSFT', ...],
      start_date='2024-01-01',
      end_date='2025-12-31',
      mode='backtest'
    )
    
    equity_history = result.equity_curve  # [{date, equity, cash, ...}, ...]
    
    db.insert_run(
      run_id=run_id,
      agent_name=agent.name,
      initial_equity=equity_history[0].equity,
      final_equity=equity_history[-1].equity,
      metrics={sharpe, return, drawdown, ...}
    )
    
    for point in equity_history:
      db.insert_equity_point(run_id, point)
```

### 2. API Serves Data
```
Frontend requests:
  GET /runs
    ↓
  API queries: SELECT * FROM agent_runs
    ↓
  Returns: [{run_id, agent_name, final_equity, sharpe_ratio, ...}]

Frontend selects runs and requests:
  GET /compare?run_ids=alpha_v1,beta_v2
    ↓
  API queries: SELECT * FROM equity_timeseries WHERE run_id IN (...)
    ↓
  Returns: {
    "runs": [
      { "run_id": "alpha_v1", "agent_name": "Alpha", "data": [{date, equity}, ...] },
      { "run_id": "beta_v2", "agent_name": "Beta", "data": [{date, equity}, ...] }
    ]
  }
```

### 3. Frontend Renders
```
app.js:
  1. Fetch /runs
  2. Display run selector (checkboxes)
  3. On selection change, fetch /compare
  4. Plot equity curves using Chart.js
  5. Show metrics cards (Sharpe, return, etc.)
```

---

## Transition to Paper Trading

When you add paper trading later, the **same database** works:

1. **Paper trading script** writes equity snapshots to `equity_timeseries` with `mode='paper'`
2. **API** can serve both modes: `/compare?run_ids=...,paper_live_run`
3. **Frontend** can toggle between backtest/paper modes at the top
4. **Live updates** use WebSocket or polling on the same tables

No schema changes needed. Just add `mode` to queries.

---

## Benefits of This Architecture

✅ **Minimal Code** — ~300 lines for milestone 1
✅ **Decoupled** — Backtest, API, UI are separate concerns
✅ **Testable** — Each component works independently
✅ **Scalable** — Easy to add agents, longer backtests, more metrics
✅ **Real-time Ready** — Paper trading uses same schema
✅ **Queryable** — SQL means custom dashboards later (Grafana, etc.)
✅ **Shareable** — Backend API can be called from other tools
✅ **Versioned** — Each run has metadata; keep history

---

## Next Steps

1. **Schema Setup**: Initialize SQLite with tables above
2. **Backtest Writer**: Build backtest_orchestrator.py to fill database
3. **API Layer**: Build FastAPI app with /runs and /compare endpoints
4. **Frontend**: Build HTML + Chart.js dashboard
5. **Test End-to-End**: Run backtest → check database → view dashboard

See individual files for implementation details.
