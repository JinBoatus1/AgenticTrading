# Agentic Trading Lab - Interface Changes (April 13, 2026)

## Changes Made

### 1. ✅ Removed Stats Cards Section
**Deleted from view:**
- Portfolio Value card
- Today's P&L card  
- Sharpe Ratio card
- Next Run time card

**Rationale:** These metrics don't apply to a benchmarking interface (only relevant for live trading)

---

### 2. ✅ Removed Signal Feed Section
**Deleted from view:**
- Signal Feed sidebar panel with market news/signals
- Refresh signals button

**Rationale:** Removed to focus on agent performance comparison in first version

---

### 3. ✅ Removed Sentiment Data
**Changes:**
- Removed decision reasoning quotes (e.g., "Momentum remains intact...")
- Kept only: Agent Name, Action, Confidence score

**Rationale:** First version focuses purely on technical decisions, no sentiment analysis

---

### 4. ✅ Combined Activity & Model Decisions
**Before:** Two separate sidebar sections
- Model Decisions cards (top)
- Activity Log (bottom)

**After:** Single "Model Activity & Decisions" section with two-column layout
- **Left column:** Model Decision cards (one agent per card, vertically stacked)
- **Right column:** Recent Activity log

**Rationale:** Better visual flow - see decisions alongside their execution history

---

## File Updates

### frontend/index.html
- Removed entire `<div class="stats-cards">` block
- Removed entire `<section class="signal-section">` block
- Removed decision-reasoning divs from decision cards
- Replaced separate Activity section with combined Activity & Decisions layout
- Changed section title to "Model Activity & Decisions"

### frontend/styles.css
- Hid `.stats-cards` (display: none)
- Hid `.signal-section` (display: none)
- Hid `.decision-reasoning` (display: none)
- Added `.activity-decisions-combined` (2-column grid layout)
- Updated `.decisions-grid` to 1-column layout (was 3-column)
- Added responsive breakpoint for combined section (1-column on mobile)

### frontend/app.js
- No changes needed (hardcoded demo data already lacks sentiment)

---

## Layout Now

```
┌─────────────────────────────────────┐
│          Header & Ticker            │
├─────────────────────────────────────┤
│       Equity Curves Chart           │
├─────────────────────────────────────┤
│ Model Activity & Decisions          │
├────────────────────┬────────────────┤
│ Decisions (left)   │ Activity (right)│
│ - DeepSeek         │ - 15:27 DeepSeek
│ - Claude           │ - 15:11 Claude │
│ - GPT              │ - 14:58 GPT    │
├────────────────────┴────────────────┤
│     Leaderboard (right sidebar)     │
└─────────────────────────────────────┘
```

---

## Next Steps

When adding sentiment data in future versions:
1. Un-hide `.decision-reasoning` in CSS
2. Re-add reasoning quotes to decision cards in HTML/JS
3. Add sentiment indicator badges (bullish/neutral/bearish)

---

## Testing

- ✅ No stats cards shown
- ✅ No signal feed shown  
- ✅ Decision cards show only: Name, Action, Confidence
- ✅ Activity and Decisions are combined in one section
- ✅ Two-column layout on desktop, single-column on mobile
