/** Shared demo storyline across Talk → Test → Race. Keep phrases identical. */

/**
 * Refined strategy prompt shown after Discord brainstorming (Talk → Test → Race).
 * Hero keeps its own frozen casual line; this is the “Lab-ready” formulation.
 */
export const STORY_PROMPT =
  "Systematically mirror material Berkshire Hathaway 13F position changes: enter and exit holdings when filings disclose significant increases or reductions. Evaluate over a 24-month window with $10,000 starting capital; report return, Sharpe ratio, and maximum drawdown versus an equal-weight buy-and-hold benchmark.";

export const STORY_AGENT_NAME = "Alpha";

export const STORY_SPECS = {
  window: "May 4–12, 2026",
  universe: "Berkshire 13F holdings",
  returnPct: "+14.2%",
  sharpe: "1.84",
  maxDd: "-8.6%",
  vsBuyHold: "+4.3%",
} as const;

export const STORY_DECISIONS = [
  {
    action: "BUY" as const,
    symbol: "OXY",
    detail: "Material increase in 13F — mirrored entry",
    type: "positive" as const,
  },
  {
    action: "HOLD" as const,
    symbol: "AAPL",
    detail: "No material Berkshire change this step",
    type: "muted" as const,
  },
  {
    action: "SELL" as const,
    symbol: "PARA",
    detail: "Material reduction in 13F — mirrored exit",
    type: "destructive" as const,
  },
];
