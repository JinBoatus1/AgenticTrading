# Design: a shared `news-story` vocabulary for AF ↔ ATL (Phase B)

**Date:** 2026-07-14
**Status:** design — awaiting review
**Repos:** Agentic FinSearch (AF, `fingpt_rcos`, PR #359) + Agentic Trading Lab (ATL, PR #107)
**Supersedes nothing; extends** `docs/integrations/finsearch-news-sentiment.md` (Phase A contract).

---

## Problem

Phase B adds a second AF endpoint, `GET /api/news/items/`, that powers the Home
panel's left column with a raw-news feed. Two things surfaced in review of ATL
PR #107:

1. **Vocabulary split.** AF's *live signals* endpoint (`/api/signals/news/`)
   names a story's title/link **`headline`/`url`**. The *new items* endpoint
   (PR #359, unmerged) names the same nouns **`title`/`link`**, and ships symbols
   as a **`tickers[]` list** where the signals side keys by a single ticker.
   ATL's `_feed_from_items` privately reconciles all three. AF therefore speaks
   two dialects for the same concepts, and the shared language lives inside one
   ATL function instead of at the source.

2. **Scope + presentation.** The items feed is broader than the Dow-30 signals
   (includes non-Dow tickers and general-market stories with `tickers: []`) and
   is **not** run through the signals relevance gate. The panel heading still
   reads "Today's signal stories," which now misdescribes the content.

The forcing function: **we intend to expand both the news sources we ingest and
the trading signals we generate.** If each new source arrives with its own field
names and ATL keeps translating per-source, the adapter becomes a growing pile of
dialect converters. The fix must put normalization at the *producer boundary*, so
one language serves every source and every consumer.

## Goal / non-goals

**Goal.** One versioned story vocabulary that (a) both AF endpoints already-or-soon
speak, (b) every future news source normalizes into at the AF boundary, and (c) is
documented so both teams cite the same contract. Keep the panel honest about what
the left column is.

**Non-goals.** Touching the **live** signals endpoint (it already speaks
`headline`/`url` — it is already conformant on the story fields). Multi-chip
ticker display in the UI. Client-side dedup. Any prod behavior change before AF
#359 ships (until then ATL's items path 404s and falls back to the Phase-A feed).

## The contract: `news-story` v1

Every AF **news** endpoint emits this story shape; every consumer reads it by key.

**Per-story fields** (each element of `items[]`, and each signals story value):

| field | type | notes |
|-------|------|-------|
| `headline` | str | the story title. (Items: renamed from on-disk `title`.) |
| `url` | str | the story link. (Items: renamed from on-disk `link`.) |
| `source` | str | outlet/provider — **distinguishes sources as we add them** |
| `published` | float | epoch seconds |
| `tickers` | str[] | 0..N symbols; `[]` = general-market. **Stays a list on the wire.** |

Items-only per-story extras (present on `/api/news/items/`, absent from a signals
story): `guid`, `description`, `score`.

**Response-level field:** `schema_version` (int) — sits at the top of the response
body next to `items[]` (items) / the artifact fields (signals), **not** inside each
story. It is the evolution valve: add fields additively, bump on a breaking change.

**Anchor rationale.** We standardize on the vocabulary the *live* endpoint already
uses rather than invent a third name. On-disk item batches (`items-*.jsonl`) stay
RSS-native (`title`/`link`) — the scraper's format is unchanged; the **API
boundary** does the rename on projection, exactly as AF's signals path already maps
raw `title` → signal `headline` internally.

**Why this scales to the two planned expansions:**
- *More sources / more coverage* — each new source is normalized to `news-story v1`
  at AF's boundary; ATL and any future consumer already understand it; `source`
  labels origin; `tickers[]` already covers multi-symbol and general-market stories;
  `schema_version` lets AF add fields without breaking readers.
- *More signal types* — signals already speak `headline`/`url`, so a story
  referenced by any signal type uses the same nouns; richer signals extend the same
  vocabulary rather than forking a new one.

## Changes by repo

### AF — `Main/backend/api/signals_views.py` (PR #359)
- Change the items projection from `{k: story[k] for k in _ITEMS_CONTRACT_FIELDS}`
  to emit `headline` (from disk `title`) and `url` (from disk `link`); keep
  `source`, `published`, `tickers`, `guid`, `description`, `score`.
- Add `schema_version: 1` to the items response body (sibling to signals'
  `schema_version`).
- Disk validation (`REQUIRED_FIELDS`, `_validate_items`, `FIELD_CAPS`) is unchanged —
  it validates the raw `title`/`link` keys; only the wire projection is renamed.
- Update `Main/backend/tests/test_news_items_endpoint.py`: `CONTRACT_KEYS` and the
  fixture builder assert `headline`/`url` and the presence of `schema_version`.
- The live `news_signals` view is **untouched**.

### ATL — `dashboard/backend/integrations/news_sentiment.py` (PR #107)
- `_feed_from_items`: read `item["headline"]` / `item["url"]` (was `title`/`link`);
  keep `tickers[0] if tickers else None` → `ticker` (null-safe). This becomes a
  near-passthrough; the malformed-item drop (KeyError/TypeError) is retained.
- Update `dashboard/backend/tests/test_news_sentiment_adapter.py` + any item
  fixtures to the `headline`/`url` wire shape.

### ATL — frontend
- `dashboard/frontend/app.html`: heading `Today's signal stories` → **`Latest news`**.
- `dashboard/frontend/home-news-signals.js`: **already fixed** — the meta line is
  built from non-empty segments (`[source, ticker, relTime].filter(Boolean).join(' · ')`)
  so a null/empty ticker or an absent relTime helper collapses cleanly instead of
  leaving a dangling " · ".

### Shared doc
- New `docs/integrations/finsearch-news-items.md`: the canonical `news-story v1`
  contract + the items endpoint (params: `?limit`; no `?tickers=` — the view does
  not filter, see below), cited by both teams. Cross-link from
  `finsearch-news-sentiment.md`.

## Deliberately settled / deferred

- **No `?tickers=` on items** — verified: AF's `news_items` view honors only
  `?limit`; its `_tickers_filter` helper is wired to the signals view only. The
  left column is *intentionally* the broad "Latest news" feed, distinct from the
  Dow-30 signals column; the heading rename makes that honest. (Reviewer finding #2
  resolved: the suggested `?tickers=` change would be a silently-ignored no-op.)
- **UI sub-label** (e.g. "not all become signals") considered for extra clarity;
  **deferred** — the rename + per-item `source` + the existing "via Agentic
  FinSearch" tag / staleness / degraded badge are judged sufficient for now.
- **Dedup** — the items endpoint sorts by `published` and does not dedup; the
  signals path runs `collapse_dup_titles`. Follow-up: confirm whether the scraper
  dedups upstream; if not, decide whether the feed needs it. Out of scope here.
- **Multi-chip ticker display** — `tickers[]` is on the wire; the panel renders a
  single collapsed chip for now (YAGNI).

## Testing

- **AF:** existing `test_news_items_endpoint.py` cases keep passing against the
  renamed keys; add an assertion that `schema_version` is present and that
  `headline`/`url` are populated from the disk `title`/`link`.
- **ATL:** adapter tests assert `_feed_from_items` maps `headline`/`url` straight
  through and still fails closed / drops malformed items; the never-regress-below-
  Phase-A fallback and the null-ticker render remain covered.

## Rollout / merge order

Both PRs are open and unmerged; the AF items endpoint is **not** in prod, so ATL's
items path currently 404s and falls back to the Phase-A representative feed — there
is no live consumer to break. Safe order: land AF #359 (endpoint emits `news-story
v1`), then ATL #107's items path lights up against it. ATL fails closed if the wire
shape is unexpected, so a temporary ordering skew degrades to the Phase-A feed
rather than erroring.

**Independent blocker (unrelated to this design):** OFL `main` CI is red from #104's
`test_engine_llm_run_metadata_snapshot`; the deploy hook gates on green tests, so
neither PR merge-and-deploys until that ~3-line test fix lands.
