# Baseline Generation Architecture

**Status:** ✅ Designed & Implemented  
**Last Updated:** April 23, 2026

---

## Core Principle

**Same baseline logic, different contexts:**

One shared `BaselineGenerator` class that creates Buy & Hold and Index curves for ANY date range and symbol set. It's called by:
- **Backtesting** (historical data, pre-computed, immutable)
- **Paper Trading** (live data, auto-updated, current)

---

## Architecture

```
┌─────────────────────────────────────┐
│ backend/baseline_generator.py       │
│                                     │
│  BaselineGenerator class:           │
│  • generate_buyhold_baseline()      │
│  • generate_index_baseline()        │
│                                     │
│  Pure logic, no DB writes           │
└─────────────────────────────────────┘
         ↑                    ↑
         │                    │
    [BACKTESTING]        [PAPER TRADING]
         │                    │
    ┌────────────────┐   ┌──────────────────┐
    │ backtest.py    │   │ paper_baselines.py│
    │ (scripts/)     │   │ (backend/)        │
    │                │   │                  │
    │ Calls:         │   │ Calls:            │
    │ generate_      │   │ generate_         │
    │ baselines()    │   │ baselines()       │
    │                │   │                  │
    │ Stores result: │   │ Stores result:    │
    │ 3 runs        │   │ 2 baseline runs   │
    │ (agent + 2BL)  │   │ (BH + Index)     │
    │ mode="backtest"│   │ mode="paper_BL"  │
    └────────────────┘   └──────────────────┘
         │                    │
         └────────┬───────────┘
                  ↓
         ┌─────────────────────┐
         │ data/backtest.db    │
         │                     │
         │ runs table:         │
         │ ├─ Agent runs (BT)  │
         │ ├─ BH baseline (BT) │
         │ ├─ Index (BT)       │
         │ ├─ BH baseline (PT) │
         │ └─ Index (PT)       │
         │                     │
         │ equity_data table:  │
         │ └─ Time-series      │
         └─────────────────────┘
```

---

## Backtesting Flow

### Step 1: Run Backtest Script
```bash
python3 scripts/backtest_hourly_agent.py --start 2026-01-01 --end 2026-04-23
```

### Step 2: What Happens

```python
# Load real Alpaca hourly data
bars_by_symbol = fetch_alpaca_bars(DJIA_30, start, end)

# Run agent backtest
agent_curve = run_agent_backtest(bars_by_symbol)

# Generate baselines from SAME data
buyhold_curve, index_curve = generate_baselines(
    bars_by_symbol=bars_by_symbol,
    start_date="2026-01-01",
    end_date="2026-04-23",
    mode="backtest"
)
```

### Step 3: Store Results

```python
db.insert_run(
    run_id="agent_20260423_...",
    agent_name="Agent",
    mode="backtest",  # ← Backtesting mode
    equity_curve=agent_curve
)

db.insert_run(
    run_id="buyhold_20260423_...",
    agent_name="BuyAndHold",
    mode="backtest",
    equity_curve=buyhold_curve
)

db.insert_run(
    run_id="djia_index_20260423_...",
    agent_name="DJIAIndex",
    mode="backtest",
    equity_curve=index_curve
)
```

### Result: 3 immutable runs in database (frozen in time)

---

## Paper Trading Flow (Future)

### Step 1: Startup
Backend calls `create_paper_baselines_if_not_exists()`:

```python
@app.on_event("startup")
async def startup_event():
    # Creates paper trading baselines
    create_paper_baselines_if_not_exists()
```

### Step 2: What It Does

```python
# Get paper account date range (today back to N days)
start_date = datetime.now() - timedelta(days=30)  # Last 30 days
end_date = datetime.now()

# Generate baselines for THIS period (using same generator!)
buyhold_curve, index_curve = generate_baselines(
    bars_by_symbol=bars_by_symbol,
    start_date=start_date,
    end_date=end_date,
    mode="paper_baseline"  # ← Paper mode
)
```

### Step 3: Store Results

```python
db.insert_run(
    run_id="paper_bh_20260423_...",
    agent_name="BuyAndHold",
    mode="paper_baseline",
    equity_curve=buyhold_curve
)

db.insert_run(
    run_id="paper_index_20260423_...",
    agent_name="DJIAIndex",
    mode="paper_baseline",
    equity_curve=index_curve
)
```

### Step 4: Live Trading Updates

```python
# Continuously update agent run only
db.insert_run(
    run_id="paper_agent_20260423_...",
    agent_name="Agent Live",
    mode="paper",
    equity_curve=agent_curve  # Updated continuously
)
```

---

## Database Schema

### Runs Table

```sql
CREATE TABLE runs (
    run_id TEXT PRIMARY KEY,
    agent_name TEXT,
    mode TEXT,  -- "backtest", "paper", "paper_baseline"
    start_date TEXT,
    end_date TEXT,
    initial_equity REAL,
    final_equity REAL,
    total_return REAL,
    sharpe_ratio REAL,
    max_drawdown REAL,
    num_trades INTEGER,
    created_at TEXT
)
```

### Modes Explained

| Mode | Context | Created By | Mutable | Time Window |
|------|---------|-----------|--------|------------|
| `backtest` | Historical analysis | backtest.py | No | Any 6+ months |
| `paper_baseline` | Current market context | paper_baselines.py | Yes (daily/weekly) | Last 30 days |
| `paper` | Live trading | paper_trading service | Yes (continuous) | Today |

### Example Data

```
run_id                 | agent_name    | mode              | start_date  | end_date    | return
-----------------------|---------------|-------------------|-------------|------------|--------
agent_20260423_...     | Agent         | backtest          | 2026-01-01  | 2026-04-23 | 0.05
buyhold_20260423_...   | BuyAndHold    | backtest          | 2026-01-01  | 2026-04-23 | -0.10
djia_20260423_...      | DJIAIndex     | backtest          | 2026-01-01  | 2026-04-23 | -0.02

paper_bh_20260423_...  | BuyAndHold    | paper_baseline    | 2026-03-24  | 2026-04-23 | -0.03
paper_dj_20260423_...  | DJIAIndex     | paper_baseline    | 2026-03-24  | 2026-04-23 | -0.01

paper_ag_20260423_...  | Agent Live    | paper             | 2026-04-20  | 2026-04-23 | 0.015
```

---

## Baseline Generator Code

Location: `backend/baseline_generator.py`

```python
class BaselineGenerator:
    """Generates baseline equity curves from real historical data."""
    
    def generate_buyhold_baseline(
        bars_by_symbol: Dict[str, pd.DataFrame],
        start_date: str,
        end_date: str,
        initial_capital: float = 100000
    ) -> List[Dict]:
        """Buy equal amounts, hold forever."""
        # Returns: [{timestamp, equity, cash, positions_value}, ...]
    
    def generate_index_baseline(
        bars_by_symbol: Dict[str, pd.DataFrame],
        start_date: str,
        end_date: str,
        initial_capital: float = 100000
    ) -> List[Dict]:
        """Equal-weight portfolio rebalanced continuously."""
        # Returns: [{timestamp, equity, cash, positions_value}, ...]

# Convenience function
def generate_baselines(...):
    """Returns: (buyhold_curve, index_curve)"""
```

---

## Dashboard Integration

### Backtesting Tab
```
Query: SELECT * FROM runs WHERE mode = 'backtest'
Shows:
  - Agent performance
  - Buy & Hold baseline (same period)
  - DJIA Index baseline (same period)
```

### Paper Trading Tab
```
Query: SELECT * FROM runs WHERE mode IN ('paper', 'paper_baseline')
Shows:
  - Agent Live (real-time)
  - Buy & Hold baseline (current 30 days)
  - DJIA Index baseline (current 30 days)
```

---

## Key Benefits

✅ **No duplication** - Same baseline logic used everywhere  
✅ **Flexible time windows** - Backtest 6 months, paper last 30 days  
✅ **Independent updates** - Paper baselines update daily, backtest stays frozen  
✅ **Clean separation** - Different modes keep contexts clear  
✅ **Reusable** - Can add more modes (monte carlo, simulation, etc.)  
✅ **Equity calculation correct** - Always `equity = cash + positions_value`

---

## Implementation Status

✅ **Phase 1: Backtesting** - DONE
- `baseline_generator.py` created
- `backtest_hourly_agent.py` refactored to use it
- 3 runs stored per backtest (agent + 2 baselines)

⏳ **Phase 2: Paper Trading** - TODO
- Update `paper_baselines.py` to use `baseline_generator`
- Add paper trading service
- Continuous equity updates
- Dashboard integration

---

## Next: Run a Backtest

```bash
cd ~/.openclaw/workspace/agentic-trading
python3 scripts/backtest_hourly_agent.py --start 2026-03-01 --end 2026-04-23
```

Expected output:
```
✅ Agent backtest complete
   • Final: $102,450
   • Return: +2.45%

✅ Buy & Hold baseline complete
   • Final: $89,800
   • Return: -10.20%

✅ DJIA Index baseline complete
   • Final: $99,350
   • Return: -0.65%
```

All 6 runs stored in database.
Open dashboard: `python3 backend/app.py` → http://localhost:8000
