# Working with Hourly Data - Recommendations

**Problem:** Alpaca free tier only has 65% hourly data coverage for DJIA stocks

**Options to fix this:**

---

## Option 1: Trade Only Most Liquid Stocks ⭐ RECOMMENDED

Instead of all 30 DJIA stocks, trade only the top 5-10 most liquid:

```python
# Instead of DJIA_30, use:
DJIA_LIQUID = [
    "AAPL",   # Most traded
    "MSFT",
    "JPM",
    "V",      # Visa - high volume
    "JNJ",
    "WMT",
    "PG",
    "KO",
    "IBM",
]
```

**Why:**
- More liquid stocks = more hourly bars in Alpaca
- Less cross-correlation (diversification still works)
- Agent still makes real trading decisions
- No fake artifacts from 35% missing data

**Pros:**
- ✅ Likely gets 90%+ hourly coverage
- ✅ Same architecture works
- ✅ Still real hourly trading
- ✅ Free (no upgrade needed)

**Cons:**
- Only 9 stocks instead of 30 (but still diverse)

---

## Option 2: Only Trade on "Complete Data Hours"

Instead of 80% threshold, require 100% of your portfolio stocks to have real data:

```python
# In run_agent_backtest():

# Filter: only keep hours where ALL symbols have real data
min_required = len(self.all_data)  # All, not 80%
filtered = []
for ts in all_timestamps:
    real_data_count = sum(1 for df in self.all_data.values() if ts in df.index)
    if real_data_count >= min_required:  # Must be 100%
        filtered.append(ts)

all_timestamps = filtered
print(f"Trading {len(all_timestamps)} hours with 100% real data")
```

**Why:**
- Only trades when you have FULL market visibility
- No blind spots
- No 35% missing data bias

**Pros:**
- ✅ Honest trading (100% data only)
- ✅ No artifacts
- ✅ Free (no upgrade needed)
- ✅ Code change is 1 line

**Cons:**
- Fewer trading opportunities (maybe 10-20% of hours have all 30 stocks)
- Agent sits idle most of the time

---

## Option 3: Upgrade Alpaca to Premium Market Data

Pay for better hourly data:

**Steps:**
1. Go to: https://app.alpaca.markets
2. Account → Data Subscriptions
3. Upgrade to "Standard" tier (~$20/month)
4. Wait for activation (usually instant)
5. Re-run backtest

**Why:**
- Premium tier has full hourly bars for all symbols
- No missing data
- Alpaca guarantees coverage

**Pros:**
- ✅ 100% hourly data coverage
- ✅ No artifacts
- ✅ No code changes needed

**Cons:**
- Costs money ($20+/month)
- Requires billing setup

---

## Option 4: Combine Options 1 + 2

Trade top 10 most liquid stocks, only on hours with 100% data:

```python
DJIA_LIQUID = ["AAPL", "MSFT", "JPM", "V", "JNJ", "WMT", "PG", "KO", "IBM", "MCD"]

# And require 100% of THOSE stocks to have data
min_required = len(DJIA_LIQUID)  # All 10, not 80% of 30
```

**Why:**
- Liquid stocks = better hourly data availability
- Requiring 100% = no blind spots
- More trading opportunities than Option 2 alone
- Free

**Pros:**
- ✅ Good data quality
- ✅ Realistic hourly trading
- ✅ No artifacts
- ✅ Free

**Cons:**
- Fewer stocks than full DJIA
- Fewer trading hours than original

---

## My Recommendation: Start with Option 1

**Use top 10 most liquid DJIA stocks:**

```python
# Replace DJIA_30 with:
DJIA_LIQUID = [
    "AAPL", "MSFT", "JPM", "V", "JNJ",
    "WMT", "PG", "KO", "IBM", "MCD"
]
```

**Why:**
1. **Free** - no upgrade needed
2. **Simple** - one variable change
3. **Realistic** - these are most-traded anyway
4. **Likely 85-90% hourly data coverage** (better than 65%)
5. **Still diversified** - 10 different sectors
6. **Agent gets more trading signals** - fewer gaps

---

## If You Want Maximum Data Quality

**Do Option 3:** Upgrade to Alpaca Standard (~$20/month)

Then you get:
- 100% hourly bars for all 30 DJIA stocks
- No code changes
- No missing data artifacts
- Complete market view

This is what professional traders use anyway.

---

## Check Data Quality First

Before deciding, let me check which DJIA stocks have the best hourly coverage:

```bash
python3 scripts/diagnose_alpaca_data.py
# Will show hourly data coverage per symbol
# We can see which 10 have best coverage
```

Then pick the top 10 by coverage.

---

## Recommendation Summary

| Option | Cost | Effort | Data Quality | Trading Frequency |
|--------|------|--------|--------------|-------------------|
| 1: Top 10 liquid | Free | 1 line | ~85% | High |
| 2: 100% hours | Free | 1 line | 100% | Low |
| 1+2: Combined | Free | 5 lines | ~95% | Medium-High |
| 3: Premium | $20/mo | Setup | 100% | High |

**Pick Option 1 or 1+2 to start. Upgrade to Option 3 later if needed.**

What would you like to do?
