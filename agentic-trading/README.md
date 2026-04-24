# Agentic Trading Lab

Multi-agent backtesting and paper trading platform with real Alpaca market data. Compare LLM trading agents (DeepSeek, Claude, GPT) on the same market stream and benchmark performance against buy-and-hold and index baselines.

## Features

✅ **Real Alpaca Data Integration** - Hourly bars from official Alpaca API  
✅ **Agent Trading Logic** - Technical indicators (RSI-14, MACD, Bollinger Bands, SMAs)  
✅ **3 Equity Curves** - Agent performance vs buy-and-hold baseline vs DJIA index  
✅ **Backtesting Engine** - 30+ days of historical data with full trade logging  
✅ **REST API** - Serve equity data to frontend dashboard  
✅ **Web Dashboard** - Chart.js visualization with light/dark theme  
✅ **Market Ticker** - Live prices from Alpaca + CoinGecko  
✅ **Market Hours Only** - Trading restricted to 9:30 AM - 4:00 PM ET  

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
│ └─ GET /ticker - Live market quotes                        │
└────────────────┬────────────────────────────────────────────┘
                 │
┌────────────────▼─────────────────────────────────────────────┐
│ Web Dashboard (frontend/)                                    │
│ ├─ index.html - Page layout                                │
│ ├─ app.js - Chart.js + API calls                           │
│ └─ styles.css - Light/dark theme styling                   │
└──────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Install Dependencies
```bash
cd agentic-trading/backend
pip install -r requirements.txt
```

### 2. Configure Alpaca Credentials
```bash
# Create credentials directory
mkdir -p credentials

# Add your Alpaca API key to:
# credentials/alpaca.json
```

Example `credentials/alpaca.json`:
```json
{
  "api_key": "YOUR_API_KEY",
  "secret_key": "YOUR_SECRET_KEY",
  "base_url": "https://paper-api.alpaca.markets"
}
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

### Dark Theme
- Light theme (default) with high contrast
- Dark theme with TradingView-like colors
- Toggle with theme button (☀️/🌙)
- Grid lines and text colors adapt to theme

## Database Schema

### `runs` table
```sql
run_id (PK), agent_name, mode, initial_equity, final_equity, 
total_return, sharpe_ratio, max_drawdown, created_at
```

### `equity_data` table
```sql
run_id (FK), timestamp, equity, cash, positions_value, daily_return
```

Modes:
- `backtest` - Historical agent performance
- `paper_baseline` - Current market context baselines
- `paper` - Live trading equity

## Performance

**30-Day Backtest (Mar 1-31, 2026)**
- Agent: -0.56% (70 trades)
- Buy-and-Hold: -5.61%
- DJIA: -5.90%
- Agent outperformed baselines in downmarket

## Future Roadmap

- [ ] Paper trading service with live execution
- [ ] Multi-agent committee (DeepSeek + Claude + GPT comparison)
- [ ] Risk metrics dashboard (Sortino, Calmar, drawdown analysis)
- [ ] Sentiment analysis integration
- [ ] Monte Carlo simulation baselines
- [ ] Full DJIA 30-stock portfolio optimization

## Development

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

# Database audit
sqlite3 data/backtest.db "SELECT agent_name, total_return FROM runs LIMIT 5;"
```

## Troubleshooting

### Charts not rendering?
- Hard refresh browser: `Ctrl+Shift+R` (or `Cmd+Shift+R` on Mac)
- Check browser console for errors
- Verify API is running: `curl http://localhost:8000/health`

### No data displayed?
- Check backtest has run: `python3 scripts/backtest_hourly_agent.py --start 2026-03-01 --end 2026-03-31`
- Verify API endpoint: `curl http://localhost:8000/runs`
- Check database: `sqlite3 data/backtest.db ".tables"`

### Alpaca credentials error?
- Verify `credentials/alpaca.json` exists
- Check API key is valid and not expired
- For paper trading, use: `https://paper-api.alpaca.markets`

## License

MIT - See LICENSE file

## Contributing

This is a personal trading lab. Pull requests and issues welcome!

---

Built with ❤️ using Alpaca API, Chart.js, and FastAPI
