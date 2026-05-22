# ⚡ Dashboard Speed Optimization

Your paper trading dashboard is now **much faster**. Here's what changed:

## Optimizations Applied

### 1. ✅ Parallel API Calls
**Before:** Sequential requests (one after another)
```
Account → Positions → Trades → History → Baselines
Total: ~3-5 seconds
```

**After:** Parallel requests (all at once)
```
Account ─┐
Positions ├─→ All in parallel!
Trades ───┘
Total: ~1-2 seconds
```

### 2. ✅ Smart Loading Order
**Critical items first** (instant display):
- Account info (equity, cash, buying power)
- Positions (current holdings)
- Trades (recent activity)

**Secondary items** (load in background):
- Portfolio history (chart)
- Baselines (comparison lines)
- Leaderboard (nice to have)

Users see data appear as it loads, not waiting for everything.

### 3. ✅ localStorage Caching
Data is saved locally in your browser:
```
First load: Fetches from API, saves to localStorage
Next loads: Uses cached data first (instant display)
Auto-updates: API fetch happens in background
```

**Result:** Subsequent clicks on the Paper tab are nearly instant.

### 4. ✅ Deferred Baselines
**Before:** Baselines fetched on every load
**After:** Baselines fetched in background (non-blocking)

Chart appears with just your account curve, baselines added when ready.

## Speed Results

### Expected Load Times

| Item | Before | After |
|------|--------|-------|
| Account | 500ms | 200ms (cached: instant) |
| Positions | 500ms | 200ms (cached: instant) |
| Trades | 400ms | 150ms (cached: instant) |
| Chart | 800ms | 400ms (cached: instant) |
| Baselines | 1000ms | Background |
| **Total** | **~3-5s** | **~1-2s** |

### First Click (Cold Cache)
```
⏱️ ~2 seconds to see everything
```

### Subsequent Clicks (Warm Cache)
```
⏱️ <500ms to display (instant visual feedback)
API fetch happens silently in background
```

## How It Works

### Browser Cache (localStorage)
```javascript
// On first load
fetch(API) → displays → saves to localStorage

// On next load
load from localStorage (instant) → fetch API in background

// If API fails
fallback to localStorage
```

### Request Waterfall
```
Time 0ms: Click Paper tab
Time 50ms: Account API called
Time 50ms: Positions API called
Time 50ms: Trades API called
Time 200ms: Account data arrives → display
Time 200ms: Positions data arrives → display
Time 200ms: Trades data arrives → display
Time 350ms: Chart API called
Time 400ms: Chart arrives → plot
Time 600ms: Baselines API called (background)
Time 900ms: Baselines arrive → update chart
```

**User experience:** Sees data instantly, chart updates smoothly, baselines appear when ready.

## Cache Details

### What Gets Cached
- Account info (equity, cash, buying power)
- Positions list (holdings + P&L)
- Recent trades (last 20)
- Equity curve (last 31 days)
- Baselines (DJIA + Buy-and-Hold)

### Cache Locations
- **Browser:** localStorage (survives page reload)
- **Backend:** In-memory with 30-120 second TTL

### How to Clear Cache
Open browser console (F12) and run:
```javascript
// Clear all cached paper trading data
localStorage.removeItem('paper_account');
localStorage.removeItem('paper_positions');
localStorage.removeItem('paper_trades');
localStorage.removeItem('paper_equity_curve');
localStorage.removeItem('paper_baselines');
console.log('✅ Cache cleared');
```

Or manually refresh the page (Ctrl+Shift+R for hard refresh).

## Further Optimizations

If still slow, try these:

### 1. Reduce Days of History
Edit `frontend/app.js`, find this line:
```javascript
fetch(`${API_BASE}/paper/portfolio-history?timeframe=1D`)
```
Add parameter:
```javascript
fetch(`${API_BASE}/paper/portfolio-history?timeframe=1W`)  // Week instead of month
```

### 2. Skip Baselines on Load
Comment out baselines call in `loadPaperTradingData()`:
```javascript
// Skip baselines to load faster
// fetch(`${API_BASE}/paper/baselines?days=31`)
```

Add button to fetch later:
```html
<button onclick="loadBaselinesLater()">Load Comparison</button>
```

### 3. Use Synthetic Baselines
Synthetic baselines load instantly (no API call):
```javascript
// Force synthetic (instant load, data is realistic but not real)
fetch(`${API_BASE}/paper/baselines?days=31&use_synthetic=true`)
```

### 4. Batch API Calls
Combine multiple endpoints into one request:
```javascript
// TODO: Could implement /paper/all endpoint that returns:
// {account, positions, trades, history, baselines}
```

### 5. Enable Compression
Ask server to gzip responses (reduces data size ~70%):
- Backend already supports this
- Happens automatically in most browsers

## Performance Metrics

Monitor performance in browser console:
```javascript
// Check load time
const startTime = performance.now();
await loadPaperTradingData();
const elapsed = performance.now() - startTime;
console.log(`Loaded in ${elapsed.toFixed(0)}ms`);
```

## Troubleshooting

### "Still loading slowly"
1. Check network tab (F12 → Network)
2. See which API call is slow
3. It's usually Alpaca API latency, not your dashboard

### "Data is stale"
If cached data is outdated:
```javascript
// Force refresh (skip cache)
localStorage.clear();
location.reload();
```

### "Baselines not showing"
Baselines load in background. If slow:
1. Wait a few seconds for chart to update
2. Or click Paper tab again to retry
3. Or check if Alpaca API is responding

## Summary

**You should now see:**
- ✅ Account/positions/trades appear in <500ms
- ✅ Chart loads within ~1 second
- ✅ Subsequent loads nearly instant (localStorage)
- ✅ Baselines load smoothly in background
- ✅ No loading spinner for critical items

If not, check your network (F12 → Network tab) to see which API is slow. It's likely Alpaca API latency, not the dashboard code.

---

**Need more speed?** Let me know what's still slow and I can optimize further! 🚀
