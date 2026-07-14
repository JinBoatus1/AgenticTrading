# FinSearch Raw News Items — the `news-story v1` Contract (Phase B)

**Audience:** both teams — AF producer (`Main/backend/api/signals_views.py`, Agentic-FinSearch) and ATL consumer (`dashboard/backend/integrations/news_sentiment.py`).
**Status (2026-07-14):** **live.** AF PR #359 shipped the producer and is deployed (wire shape verified against prod). The ATL consumer lands in PR #110 — ATL PR #107 merged at a commit that predated the `headline`/`url` rename, so between the two merges the adapter read the retired keys and the panel silently served the Phase-A fallback; #110 is the fix.
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
top of the response body, **not** inside each story. Intended evolution valve:
fields are added additively; a breaking change bumps the version.

> **It is a producer-side convention only — no consumer reads it today.** ATL
> parses stories by key and ignores `schema_version` entirely. So a v2 that
> renamed a field would not be *detected* by the version number; every story
> would simply fail to project and the panel would fall back to Phase A. That is
> fail-closed, which is why it is tolerable, but the version number does no work
> in preventing it — what actually surfaces such a break is the drift check in
> `get_latest_panel_payload` (0 usable entries from a non-empty batch), which
> logs an `ERROR` **and** escalates the payload to `degraded` so the panel badge
> says so. Don't mistake the presence of this field for a consumer that gates on
> it.

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
- `tickers[]` stays a list on the wire; ATL's panel currently collapses it to `tickers[0] | null` for its single chip (multi-chip display deferred). A `[]` general-market story therefore renders with **no ticker chip** — the meta line is joined from non-empty segments, so the separator collapses with it.
- **Alarm on wholesale drift, in the logs *and* in the UI.** Because the fallback is silent by design, a consumer must distinguish *one* bad story from *the contract moved*. ATL logs `ERROR` when a non-empty batch projects to zero usable entries; an empty batch is "no news", not drift. This is the safety net the 2026-07-14 rename slipped past. The check (`_alarm_if_all_dropped`) is a property of *projection*, not of the items endpoint, so it guards the Phase-A fallback too — that path needs it at least as much, since when the signals vocabulary drifts there is nothing left to fall back to and the feed goes blank rather than merely stale.
- **Drift escalates `status` to `degraded`.** A log line only reaches whoever is reading logs, and in 2026-07-14 nobody was — the panel looked healthy, because the fallback made it look healthy. So drift also sets `status: "degraded"` and appends a reader-facing `status_reason` (`news feed incomplete — upstream story format changed`), which the Home panel already renders as a badge. Two rules keep the badge worth reading: it stays dark on a quiet news day (an empty artifact drops nothing, so it isn't drift), and a drift reason is *appended to* the producer's own `status_reason` rather than replacing it — "a source timed out" and "the wire shape moved" are independent failures and the badge should not let the later one erase the earlier.
- **Pin the wire shape in a fixture, not in inline test dicts.** ATL records it once in `dashboard/backend/tests/fixtures/items-wire-fixture.json` (key set verified against prod) and drives the adapter's happy path from it, so a rename must visibly edit that file. Fixtures written inline beside the code they test drift *with* the code and stay green.

## Known gap

Nothing in ATL's test suite can *catch* a producer rename — the producer is mocked, so AF and ATL can only drift apart between deploys. The fixture makes the assumed shape reviewable and the drift `ERROR` makes a break visible within one poll, but neither is a cross-repo contract test. If this seam breaks a third time, the fix is a canary that exercises the real endpoint (or an AF-published fixture ATL diffs in CI), not more mocked coverage.

## Traceability

| Decision | Anchor |
|----------|--------|
| Vocabulary anchored to the live signals endpoint's nouns | design spec §"Anchor rationale" |
| Rename at producer boundary, disk stays RSS-native | design spec §"The contract"; AF `signals_views.py` `_ITEMS_WIRE_RENAMES` |
| Broad feed, no `?tickers=` | design spec §"Deliberately settled / deferred" |
| Fallback/fail-closed consumer behavior | ATL `news_sentiment.py` `get_latest_panel_payload` docstring |
| Drift `ERROR` vs. per-item warning | ATL `test_items_all_dropped_logs_drift_error` / `test_partial_malformed_items_does_not_log_drift_error` |
| Drift alarm covers the fallback, not just items | ATL `_alarm_if_all_dropped`; `test_representative_fallback_all_dropped_logs_drift_error` |
| "Non-empty raw" half of the predicate (no crying wolf on a quiet news day) | ATL `test_items_empty_list_does_not_log_drift_error` / `test_empty_signals_artifact_does_not_log_drift_error` |
| Recorded wire shape + its coherence with the signals fixtures | ATL `items-wire-fixture.json`; `test_news_sentiment_fixture.py` |
