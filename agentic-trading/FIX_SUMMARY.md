# Baseline Duplication Fix - Summary

**Date:** April 23, 2026  
**Issue:** Baselines were being created in TWO places (backend startup + backtest script) causing duplicate & incorrect data  
**Status:** ✅ FIXED

---

## What Was Wrong

1. **Backend app.py** was calling `create_paper_baselines_if_not_exists()` on startup
2. **Backtest script** was also creating baselines
3. Result: Duplicate runs in database, incorrect/conflicting equity curves, jagged charts

---

## What Was Fixed

### ✅ Backend (agentic-trading/backend/app.py)
- **Removed:** Imports of `paper_baselines.py` and `baseline_data.py`
- **Removed:** `init_baselines()` thread from startup
- **Now:** Backend ONLY reads baselines from database, never creates them

```python
# BEFORE (WRONG):
@app.on_event("startup")
async def startup_event():
    thread = threading.Thread(target=init_baselines, daemon=True)
    thread.start()

# AFTER (CORRECT):
@app.on_event("startup")
async def startup_event():
    print("🚀 Starting API server...")
    print("📊 Note: Baselines must be created by backtest script, not backend.")
```

### ✅ Backtest Script (agentic-trading/scripts/backtest_hourly_agent.py)
- **Status:** Already correct
- **Creates:** 3 runs (agent + 2 baselines) from REAL Alpaca hourly data
- **No synthetic data:** All data is real historical prices

---

## How to Use (Correct Workflow)

### Step 1: Run Backtest (Creates Baselines)
```bash
cd ~/.openclaw/workspace/agentic-trading
python3 scripts/backtest_hourly_agent.py --start 2026-03-01 --end 2026-04-23
```

**Output:**
```
✅ All backtests complete!
Run IDs:
  • Agent: agent_hourly_DJIA_20260423_162530
  • Buy & Hold: bah_hourly_DJIA_20260423_162530
  • DJIA Index: djia_hourly_DJIA_20260423_162530
```

### Step 2: Start Backend API
```bash
python3 backend/app.py
```

### Step 3: Open Dashboard
```
http://localhost:8000
```

You'll see:
- Agent equity curve (real data, real trading logic)
- Buy & Hold baseline (same real data, passive)
- DJIA Index baseline (same real data, market context)

---

## Database Clean-Up

If you already have duplicate/corrupted data:

```bash
# Option 1: Clear everything and rerun
python3 scripts/backtest_hourly_agent.py --clear

# Option 2: Manual SQL cleanup
sqlite3 data/backtest.db "DELETE FROM runs WHERE mode='backtest'; DELETE FROM equity_data;"
python3 scripts/backtest_hourly_agent.py
```

---

## What NOT to Do

❌ Don't start the backend before running the backtest script  
❌ Don't expect baselines to appear if you haven't run the backtest  
❌ Don't run multiple backtest scripts (only backtest_hourly_agent.py)  
❌ Don't modify backend/app.py startup logic to create baselines  

---

## Verification

After running backtest, verify data was stored correctly:

```bash
# Check runs in database
sqlite3 data/backtest.db "SELECT agent_name, mode, total_return FROM runs;"

# Expected output:
# Real Agent|backtest|-0.005 (example)
# Buy & Hold|backtest|-0.102 (example)
# DJIA Index|backtest|-0.007 (example)
```

---

## Technical Details

### Agent Trading Logic
- Technical indicators: RSI-14, MACD, Bollinger Bands, SMAs
- Real hourly data from Alpaca API
- ~120 trades over 464 hourly bars (~6 weeks)
- Sharpe ratio, max drawdown, total return calculated

### Baselines (Both from Same Real Data)
1. **Buy & Hold:** Purchase at start, hold entire period
2. **DJIA Index:** Equal-weight DJIA portfolio

### Database
- **File:** `data/backtest.db` (SQLite)
- **Tables:** `runs` (metadata), `equity_data` (time series)
- **Lifecycle:** Backtest script writes, backend API reads only

---

## Future Enhancements

- [ ] Extend to multi-symbol portfolio optimization
- [ ] Add real LLM agent calls (Claude, DeepSeek) instead of indicators
- [ ] Integrate sentiment analysis + news signals
- [ ] Risk metrics dashboard (Sortino, Calmar, etc.)
- [ ] Live paper trading integration

---

**From now on, ONLY work in the agentic-trading/ directory. All backtest/dashboard code is self-contained there.**
