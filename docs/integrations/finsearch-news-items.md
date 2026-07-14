# FinSearch Raw News Items — the `news-story v1` Contract (Phase B)

**Audience:** both teams — AF producer (`Main/backend/api/signals_views.py`, Agentic-FinSearch) and ATL consumer (`dashboard/backend/integrations/news_sentiment.py`).
**Status (2026-07-14):** adopted by AF PR #359 + ATL PR #107; merge order is AF first (ATL fails closed to the Phase-A feed until then).
**Design rationale:** `docs/superpowers/specs/2026-07-14-finsearch-news-story-contract-design.md`.
**Companion:** [`finsearch-news-sentiment.md`](finsearch-news-sentiment.md) — Phase A, the signals endpoint this contract's vocabulary is anchored to.

---

## The `news-story v1` vocabulary

Every AF **news** endpoint emits stories in this shape; every consumer reads it
by key. New sources are normalized into it **at AF's API boundary** — consumers
never see per-source dialects.

**Per-story fields** (each element of `items[]`; a signals story speaks the same nouns):

| field | type | notes |
|-------|------|-------|
| `headline` | str | story title (disk-native `title`, renamed at the boundary) |
| `url` | str | story link (disk-native `link`, renamed at the boundary) |
| `source` | str | outlet/provider — distinguishes sources as they're added |
| `published` | float | epoch seconds |
| `tickers` | str[] | 0..N symbols; `[]` = general-market story |

Items-only per-story extras (absent from a signals story): `guid`, `description`, `score`.

**Response-level field:** `schema_version` (int, currently `1`) — sits at the
top of the response body, **not** inside each story. Evolution valve: fields
are added additively; a breaking change bumps the version.

**Disk vs. wire:** on-disk batches (`items-*.jsonl`) stay RSS-native
(`title`/`link` — the scraper's format, validated by the ported
`validation_gate` trust boundary). Only the wire projection renames.

## `GET /api/news/items/` (AF)

The newest raw items batch — **broad by design**: not run through the signals
relevance gate, may include non-Dow tickers and general-market stories. It
powers ATL's Home-panel "Latest news" column.

- **Auth:** Bearer token (same gate as `/api/signals/news/`); missing/wrong → 401.
- **Params:** `?limit=` only — default 50, clamped to [1, 200]; non-integer → `400 {"error": "bad_limit"}`. There is deliberately **no `?tickers=` filter** (the sibling signals endpoint has one; this feed is intentionally unfiltered).
- **Response 200:**

  ```json
  {
    "schema_version": 1,
    "items": [ { "guid": "…", "headline": "…", "url": "…", "source": "…",
                 "published": 1752473600.0, "description": "…",
                 "tickers": ["AAPL"], "score": 0.7 } ],
    "count": 1,
    "batch": "items-2026-07-14.jsonl"
  }
  ```

  Items sorted newest-first by `published`. No dedup (unlike the signals path's `collapse_dup_titles`).
- **Fail-closed 404** `{"error": "no_items"}`: unconfigured/empty dir, unreadable/oversized/poisoned batch, or zero valid stories. Never 500s on bad input.
- **Caching:** `Cache-Control: public, max-age=300`; `ETag` (varies with batch + limit) and `Last-Modified` (default-limit variant only) support conditional GET → 304.

## Consumer rules (ATL, and any future reader)

- Read stories **by key**; ignore unknown keys (additive evolution).
- Fail closed: a malformed **item** is dropped (logged), a malformed **body** falls back to the Phase-A representative feed — the panel never regresses below Phase A and never errors out.
- `tickers[]` stays a list on the wire; ATL's panel currently collapses it to `tickers[0] | null` for its single chip (multi-chip display deferred).

## Traceability

| Decision | Anchor |
|----------|--------|
| Vocabulary anchored to the live signals endpoint's nouns | design spec §"Anchor rationale" |
| Rename at producer boundary, disk stays RSS-native | design spec §"The contract"; AF `signals_views.py` `_ITEMS_WIRE_RENAMES` |
| Broad feed, no `?tickers=` | design spec §"Deliberately settled / deferred" |
| Fallback/fail-closed consumer behavior | ATL `news_sentiment.py` `get_latest_panel_payload` docstring |
