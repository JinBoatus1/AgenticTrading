# Agentic Trading Dashboard - Quick Start Guide

This is your complete implementation for milestone 1: **Backtesting with Multi-Agent Equity Curves**.

---

## 🎯 What You Have

### Architecture (3 layers)
1. **Backtest Script** — Runs agents, generates equity curves
2. **Backend API** — Serves data from SQLite database
3. **Frontend Dashboard** — Visualizes multi-line equity chart

### Files

```
workspace/
├── BACKTEST_ARCHITECTURE.md          ← Design documentation
├── BACKTEST_QUICKSTART.md            ← This file
├── scripts/
│   └── backtest_orchestrator.py      ← Run backtests
├── backend/
│   ├── app.py                        ← FastAPI server
│   ├── database.py                   ← SQLite layer
│   ├── models.py                     ← (Optional) Pydantic models
│   └── requirements.txt               ← Dependencies
├── frontend/
│   ├── index.html                    ← Dashboard HTML
│   ├── app.js                        ← Chart.js logic
│   └── styles.css                    ← Styling
└── data/
    └── backtest.db                   ← SQLite database (auto-created)
```

---

## 🚀 Quick Start (5 minutes)

### Step 1: Install Dependencies

```bash
cd workspace/backend
pip install -r requirements.txt
```

### Step 2: Run Backtests

```bash
# Run all agents (uses mock data for demo)
python3 scripts/backtest_orchestrator.py

# Or specific symbols and dates
python3 scripts/backtest_orchestrator.py --symbols AAPL MSFT --start 2024-01-01 --end 2024-12-31

# Or single agent only
python3 scripts/backtest_orchestrator.py --agent "Alpha Agent"

# Clear old data first
python3 scripts/backtest_orchestrator.py --clear
```

**Expected output:**
```
🎯 Agentic Trading Backtest Orchestrator
======================================================================

Running backtest: Alpha Agent
   Symbols: AAPL, MSFT, GOOGL, JPM, WMT
   Period: 2024-01-01 → 2024-12-31
   
   ✅ Backtest complete!
   • Total Return: 15.32%
   • Sharpe Ratio: 1.23
   • Max Drawdown: -8.45%
   • Equity Points: 252
   • Run ID: alpha_agent_20260410_154530
```

Backtests are stored in `data/backtest.db` automatically.

### Step 3: Start API Server

```bash
python3 backend/app.py
```

Or with `uvicorn`:
```bash
uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000
```

**Expected output:**
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

### Step 4: Open Dashboard

Open your browser to:
```
http://localhost:8000/static/index.html
```

Or directly via FastAPI docs:
```
http://localhost:8000/docs
```

### Step 5: Select & Plot

1. Toggle between "Backtest" and "Paper" modes
2. Check boxes next to agents you want to compare
3. Click "Plot Curves"
4. View equity curves, metrics, and leaderboard

---

## 📊 API Endpoints

All endpoints return JSON. Base URL: `http://localhost:8000`

### Get All Runs
```bash
curl http://localhost:8000/runs
curl http://localhost:8000/runs?mode=backtest
curl http://localhost:8000/runs?mode=paper
```

Response:
```json
[
  {
    "run_id": "alpha_agent_20260410_154530",
    "agent_name": "Alpha Agent",
    "mode": "backtest",
    "start_date": "2024-01-01",
    "end_date": "2024-12-31",
    "initial_equity": 100000,
    "final_equity": 115320,
    "total_return": 0.1532,
    "sharpe_ratio": 1.23,
    "max_drawdown": -0.0845,
    "num_trades": 42,
    "created_at": "2026-04-10T15:45:30"
  }
]
```

### Get Single Run Metadata
```bash
curl http://localhost:8000/runs/{run_id}
```

### Get Equity Curve
```bash
curl http://localhost:8000/runs/{run_id}/equity
```

Response:
```json
{
  "run_id": "alpha_agent_20260410_154530",
  "agent_name": "Alpha Agent",
  "data": [
    {
      "timestamp": "2024-01-02",
      "equity": 100500,
      "cash": 30000,
      "positions_value": 70500,
      "daily_return": 0.005
    },
    ...
  ],
  "metrics": {
    "total_return": 0.1532,
    "sharpe_ratio": 1.23,
    "max_drawdown": -0.0845,
    "num_trades": 42
  }
}
```

### Compare Multiple Runs
```bash
curl "http://localhost:8000/compare?run_ids=run1,run2,run3"
```

Response:
```json
{
  "runs": [
    {
      "run_id": "run1",
      "agent_name": "Alpha Agent",
      "data": [...],
      "metrics": {...}
    },
    ...
  ],
  "summary": {
    "num_runs": 3,
    "best_performer": "Alpha Agent",
    "best_return": 0.1532
  }
}
```

---

## 🔧 Customization

### Add/Modify Agents

Edit `scripts/backtest_orchestrator.py`:

```python
AGENT_CONFIGS = [
    {
        "name": "My Custom Agent",
        "type": "custom",
        "description": "My strategy description",
        "config": {
            "param1": "value1",
            "param2": "value2"
        }
    },
    # ... more agents
]
```

### Change Database Location

Edit `backend/database.py`:

```python
DB_PATH = Path.home() / "path" / "to" / "your" / "backtest.db"
```

### Change API Port

Edit the port in Step 3 (default 8000).

Or programmatically:
```python
# In backend/app.py
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9000)  # Change port
```

### Modify Dashboard Styling

Edit `frontend/styles.css` to customize colors, fonts, layout, etc.

---

## 🔗 Integration with AgenticTrading

Replace the mock orchestrator with your real implementation:

**In `scripts/backtest_orchestrator.py`:**

```python
# Replace this:
from agentic_trading import Orchestrator

class BacktestRunner:
    def __init__(self, symbols, start_date, end_date):
        self.orchestrator = Orchestrator()  # Real orchestrator
    
    def run_agent_backtest(self, agent_config, verbose=True):
        # ... same structure, but call real orchestrator
        result = self.orchestrator.run_pipeline(
            symbols=self.symbols,
            start_date=self.start_date,
            end_date=self.end_date,
            agent_config=agent_config,
            mode="backtest"
        )
```

The `result` object should contain:
```python
{
    "equity_curve": [
        {
            "timestamp": "YYYY-MM-DD",
            "equity": <float>,
            "cash": <float>,
            "positions_value": <float>,
            "daily_return": <float>
        },
        ...
    ],
    "metrics": {
        "total_return": <float>,
        "sharpe_ratio": <float>,
        "max_drawdown": <float>,
        "num_trades": <int>
    }
}
```

---

## 📈 Next Steps (For Milestone 2+)

### Add Paper Trading
1. Update `scripts/` with a `paper_trader.py` script
2. Write live equity snapshots to database with `mode="paper"`
3. Frontend automatically supports live mode (toggle at top)

### Add Trade Log
1. Populate `trades` table in SQLite
2. Add `/runs/{run_id}/trades` endpoint
3. Add "Recent Orders" section to dashboard

### Add Risk Dashboard
1. Store additional metrics (Var, Sortino, Calmar)
2. Add new section for risk metrics cards
3. Visualize portfolio heat, correlation stress, etc.

### Add Signal Feed
1. Store signal generation in new table
2. Create `/signals` endpoint
3. Display real-time alerts and reasoning

---

## 🧪 Testing

### Test Database

```bash
python3 -c "
import sys
sys.path.insert(0, 'backend')
from database import db

# Check all runs
runs = db.get_all_runs()
print(f'Total runs: {len(runs)}')
for run in runs:
    print(f'  {run[\"run_id\"]}: {run[\"agent_name\"]}')

# Check specific equity curve
if runs:
    curve = db.get_equity_curve(runs[0]['run_id'])
    print(f'Equity points: {len(curve)}')
"
```

### Test API

```bash
# Start server first: python3 backend/app.py

# In another terminal:
curl http://localhost:8000/runs | python3 -m json.tool
```

### Test Dashboard

1. Open browser DevTools (F12)
2. Check Console for JavaScript errors
3. Check Network tab for API calls

---

## 🐛 Troubleshooting

### "Module not found: fastapi"
```bash
pip install fastapi uvicorn pydantic
```

### "Address already in use" (port 8000)
```bash
# Use different port:
python3 backend/app.py --port 9000
# or kill process:
lsof -i :8000 | grep LISTEN | awk '{print $2}' | xargs kill
```

### "Can't connect to API" in dashboard
1. Ensure API is running (`python3 backend/app.py`)
2. Check browser console (F12) for CORS errors
3. Verify URL is correct (`http://localhost:8000`)
4. Check firewall/network settings

### Empty dashboard (no runs)
1. Run backtest script first: `python3 scripts/backtest_orchestrator.py`
2. Check database exists: `ls -la data/backtest.db`
3. Verify API can read it: `curl http://localhost:8000/runs`

### Charts not displaying
1. Check browser console for JavaScript errors
2. Verify selected runs (must select at least 2)
3. Check "Plot Curves" button was clicked
4. Try different browser (Chrome, Firefox, Safari)

---

## 📝 Architecture Recap

**Data Flow:**
```
Script (backtest_orchestrator.py)
    ↓ equity data
Database (SQLite)
    ↓ queries
API (FastAPI)
    ↓ JSON
Frontend (HTML + Chart.js)
    ↓ renders
Dashboard
```

**Key Design Decisions:**
- ✅ SQLite: Simple, portable, no external DB needed
- ✅ REST API: Easy to extend, decoupled from frontend
- ✅ Same schema for backtest + paper: Seamless integration later
- ✅ Chart.js: Lightweight, no build step, works everywhere

---

## 💡 Pro Tips

1. **Batch runs**: Run multiple agents at once, then compare side-by-side
2. **Export data**: Query SQLite directly for custom analysis
3. **Version runs**: Use run metadata timestamps to keep history
4. **Automate**: Wrap backtest script in a cron job
5. **Share**: Deploy API to cloud, dashboard works anywhere

---

## 📚 Files Reference

| File | Purpose |
|------|---------|
| `BACKTEST_ARCHITECTURE.md` | Full design doc (database schema, data flow) |
| `scripts/backtest_orchestrator.py` | Main backtest runner, agent orchestration |
| `backend/app.py` | FastAPI server with REST endpoints |
| `backend/database.py` | SQLite CRUD operations |
| `backend/requirements.txt` | Python dependencies |
| `frontend/index.html` | Dashboard HTML structure |
| `frontend/app.js` | Dashboard logic (API calls, chart rendering) |
| `frontend/styles.css` | Dashboard styling |

---

## 🎉 You're Ready!

Follow the **Quick Start** section above and you'll have a working dashboard in minutes.

Questions? Check the API docs at `http://localhost:8000/docs` (auto-generated by FastAPI).

Happy backtesting! 🚀
