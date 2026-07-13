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


def test_fixture_matches_contract_essentials():
    body = load_signals_fixture()
    assert body["schema_version"] == 1
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
