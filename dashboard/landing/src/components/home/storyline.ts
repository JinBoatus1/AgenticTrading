/** Shared demo storyline across Talk → Test → Race. Keep phrases identical. */

/**
 * Refined strategy prompt shown after Discord brainstorming (Talk).
 * Hero keeps its own frozen casual line; this is the Lab-ready formulation.
 */
export const STORY_PROMPT =
  "Systematically mirror material Berkshire Hathaway 13F position changes: enter and exit holdings when filings disclose significant increases or reductions. Evaluate over a one-month window with $10,000 starting capital; report return, Sharpe ratio, and maximum drawdown versus DJIA, S&P 500, and equal-weight buy-and-hold baselines.";

export const STORY_AGENT_NAME = "Alpha";

/** Experiment settings for the Test (Part 2) run report. */
export const STORY_SPECS = {
  timePeriod: "Apr 15 – May 15, 2026",
  timePeriodLabel: "1 month",
  initialCapital: "$10,000",
  initialCapitalNum: 10_000,
  universe: "DJIA 30",
  baselines: ["DJIA", "S&P 500", "Buy & Hold"] as const,
  model: "Claude Sonnet 4.6",
  estTokenCost: "$0.38",
  estTokens: "412k in · 28k out",
  returnPct: "+14.2%",
  sharpe: "1.84",
  maxDd: "-8.6%",
  vsBuyHold: "+4.3%",
  trades: 22,
  avgHoldDays: 63,
  /** @deprecated use timePeriod — kept for older refs */
  window: "Apr 15 – May 15, 2026",
} as const;

export const STORY_DECISIONS = [
  {
    step: 12,
    time: "Apr 22 · 14:00 ET",
    action: "BUY" as const,
    symbol: "OXY",
    shares: 48,
    price: "$62.40",
    detail: "Material increase in latest 13F — mirrored entry at open of next session",
    type: "positive" as const,
  },
  {
    step: 41,
    time: "May 2 · 15:00 ET",
    action: "HOLD" as const,
    symbol: "AAPL",
    shares: 36,
    price: "$198.20",
    detail: "No material Berkshire change this step — position unchanged",
    type: "muted" as const,
  },
  {
    step: 58,
    time: "May 9 · 14:00 ET",
    action: "SELL" as const,
    symbol: "PARA",
    shares: 120,
    price: "$11.85",
    detail: "Material reduction in 13F — mirrored full exit",
    type: "destructive" as const,
  },
];
