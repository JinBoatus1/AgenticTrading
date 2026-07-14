import json
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def load_signals_fixture() -> dict:
    return json.loads((FIXTURES / "signals-fixture.json").read_text())


def load_signals_wire_fixture() -> dict:
    """The stripped-and-injected shape the bearer-gated HTTP endpoint returns,
    as distinct from the raw on-disk artifact (`load_signals_fixture`). Per the
    contract (docs/integrations/finsearch-news-sentiment.md §"Producer response
    shape"): the view drops `generator`/`model`/`prompt_version` via
    `_PUBLIC_STRIP` and appends a server-computed `staleness_hours` last. The
    adapter reads this shape, so its `staleness_hours` / `degraded` branches are
    only reachable through this fixture — the on-disk one omits `staleness_hours`
    and is `status: ok`."""
    return json.loads((FIXTURES / "signals-wire-fixture.json").read_text())


def load_items_wire_fixture() -> dict:
    """The `GET /api/news/items/` response shape (news-story v1), the single
    recorded record of what the adapter's items path parses — see
    docs/integrations/finsearch-news-items.md.

    Content is synthetic (like the signals fixtures) but the KEY SET is the one
    the live producer emits, verified against prod 2026-07-14. That verification
    is the point: before this fixture existed the items shape lived only as
    inline dicts inside individual tests, so when AF renamed title/link ->
    headline/url the tests and the adapter drifted together and stayed green
    while prod silently served the Phase-A fallback.

    This is the batch the signals fixtures were derived FROM: `batch` matches
    their `source_items`, and the 6 stories reconcile with their diagnostics
    (stories_total 6; MSFT/NVDA signalled, AAPL/GOOGL not; one MSFT near-dup) —
    so the pair also demonstrates the Phase-B thesis that the items feed is
    broader than the signals it feeds."""
    return json.loads((FIXTURES / "items-wire-fixture.json").read_text())


# Every key `GET /api/news/items/` puts on a story, per the news-story v1 table
# in docs/integrations/finsearch-news-items.md. The first five are the shared
# vocabulary; guid/description/score are the items-only extras.
ITEMS_STORY_KEYS = {"headline", "url", "source", "published", "tickers",
                    "guid", "description", "score"}


def test_items_wire_fixture_matches_contract_essentials():
    """Pins the items fixture to the documented contract, so a future producer
    rename has to change this file — and be seen in review — rather than being
    absorbed silently into whichever test dict happened to mention the field."""
    body = load_items_wire_fixture()
    assert body["schema_version"] == 1
    assert set(body) == {"schema_version", "items", "count", "batch"}
    items = body["items"]
    assert isinstance(items, list) and items
    assert body["count"] == len(items)
    for item in items:
        assert set(item) == ITEMS_STORY_KEYS
        assert isinstance(item["headline"], str) and item["headline"]
        assert isinstance(item["url"], str) and item["url"]
        assert isinstance(item["published"], float)
        assert isinstance(item["tickers"], list)
    # newest-first, as the endpoint sorts it
    published = [i["published"] for i in items]
    assert published == sorted(published, reverse=True)


def test_items_wire_fixture_does_not_speak_the_retired_vocabulary():
    """Regression guard on the 2026-07-14 incident: `title`/`link` are the
    on-disk RSS-native names and must never reappear on the wire fixture — the
    rename happens at AF's boundary, so a consumer that sees them is looking at
    a pre-v1 shape."""
    for item in load_items_wire_fixture()["items"]:
        assert "title" not in item
        assert "link" not in item


def test_items_fixture_is_the_batch_the_signals_fixture_came_from():
    """Content-parity guard across the fixture pair (mirrors the signals
    wire/on-disk parity test below): if these drift apart, the items fixture
    stops being a coherent producer batch and the Phase-B breadth it
    demonstrates goes hollow."""
    signals_body = load_signals_fixture()
    items_body = load_items_wire_fixture()
    assert items_body["batch"] == signals_body["source_items"]
    assert items_body["count"] == signals_body["diagnostics"]["stories_total"]
    # every signalled story must exist in the batch, keyed by guid
    by_guid = {i["guid"]: i for i in items_body["items"]}
    for sym, sig in signals_body["signals"].items():
        story = by_guid[sig["guid"]]
        assert story["headline"] == sig["headline"]
        assert story["url"] == sig["url"]
        assert story["source"] == sig["source"]
        assert story["published"] == sig["published"]
        assert sym in story["tickers"]
    # ...and the batch must be strictly broader than the signals (the Phase-B point)
    assert len(items_body["items"]) > len(signals_body["signals"])


def test_fixture_matches_contract_essentials():
    body = load_signals_fixture()
    assert body["schema_version"] in (1, 2)  # transitional; PR-2 pins == 2
    assert isinstance(body["signals"], dict) and body["signals"]
    sample = next(iter(body["signals"].values()))
    for field in ("sentiment", "score", "rationale", "headline", "source",
                  "url", "published", "guid", "n_articles"):
        assert field in sample


def test_wire_fixture_reflects_public_projection():
    """Guards the wire/on-disk distinction the adapter depends on: the wire
    shape carries `staleness_hours` and omits the three fields `_PUBLIC_STRIP`
    removes. If this drifts, the staleness/degraded coverage below goes hollow."""
    wire = load_signals_wire_fixture()
    assert wire["staleness_hours"] is not None            # injected on the wire
    for stripped in ("generator", "model", "prompt_version"):
        assert stripped not in wire                        # dropped by _PUBLIC_STRIP
    assert isinstance(wire["signals"], dict) and wire["signals"]


def test_wire_fixture_is_base_minus_strip_plus_staleness():
    """Content-parity guard: the wire fixture must equal the on-disk fixture
    modulo the documented transform (drop the three _PUBLIC_STRIP fields, append
    `staleness_hours`). The `signals` blocks are byte-identical today; without
    this assertion the two could silently diverge and quietly hollow out the
    wire-shape coverage that depends on them matching."""
    base = load_signals_fixture()
    wire = load_signals_wire_fixture()
    expected = {k: v for k, v in base.items()
                if k not in ("generator", "model", "prompt_version")}
    expected["staleness_hours"] = wire["staleness_hours"]
    assert wire == expected
