/** Shared demo storyline across Talk → Test → Race. Keep phrases identical. */

/** Same plain-language idea as the /app home playground demo. */
export const STORY_PROMPT =
  "I want to follow Warren Buffett. If Berkshire makes a move, copy the move and tell me how it goes.";

export const STORY_AGENT_NAME = "Your agent";

export const STORY_SPECS = {
  window: "May 4–12, 2026",
  universe: "Berkshire holdings",
  returnPct: "+14.2%",
  sharpe: "1.84",
  maxDd: "-8.6%",
  vsBuyHold: "+4.3%",
} as const;

export const STORY_DECISIONS = [
  {
    action: "BUY" as const,
    symbol: "OXY",
    detail: "Berkshire added — copied the buy",
    type: "positive" as const,
  },
  {
    action: "HOLD" as const,
    symbol: "AAPL",
    detail: "No new Berkshire move this step",
    type: "muted" as const,
  },
  {
    action: "SELL" as const,
    symbol: "PARA",
    detail: "Berkshire trimmed — copied the exit",
    type: "destructive" as const,
  },
];
