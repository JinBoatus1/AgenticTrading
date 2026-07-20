/** Shared demo storyline across Talk → Test → Race. Keep phrases identical. */

/** Plain-language idea — no tickers, indicators, or finance jargon. */
export const STORY_PROMPT =
  "Follow Trump on X and buy whatever he tweets about";

export const STORY_AGENT_NAME = "Your agent";

export const STORY_SPECS = {
  window: "May 4–12, 2026",
  universe: "US stocks he mentions",
  returnPct: "+14.2%",
  sharpe: "1.84",
  maxDd: "-8.6%",
  vsBuyHold: "+4.3%",
} as const;

export const STORY_DECISIONS = [
  {
    action: "BUY" as const,
    symbol: "DJT",
    detail: "New post mentioned the stock — bought a small position",
    type: "positive" as const,
  },
  {
    action: "HOLD" as const,
    symbol: "Cash",
    detail: "No new stock names in today's posts",
    type: "muted" as const,
  },
  {
    action: "SELL" as const,
    symbol: "TSLA",
    detail: "He walked back yesterday's mention — exited",
    type: "destructive" as const,
  },
];
