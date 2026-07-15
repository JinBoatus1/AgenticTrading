"""PR-2 of the FinSearch score-field disambiguation (see FinSearch spec
2026-07-14-score-field-disambiguation-design.md): the transitional v1 `score`
fallback is gone, and reading v1 is now an error rather than a kindness.

Signals v2 is a HARD rename, not a dual-write: signals-v2.schema.json requires
`sentiment_score` and sets additionalProperties:false, and FinSearch renames at
its API boundary so `score` never reaches the wire — whether the artifact is
read as latest or via `?as_of`, and whether the artifact on disk is native v2
or a normalized v1. There is no grace period left to be tolerant of, so a
payload still carrying `score` is not an old-but-valid producer worth
accommodating; it is a broken one. Tolerating it would only paint a plausible
number onto the panel while hiding the breakage.

Note `_project_entry` still EMITS the internal key `score`. That is deliberate,
not a missed rename: api/v2/models.py's NewsSentimentEntry validates the
internal envelope, whose vocabulary is decoupled from the wire's by design.
This module is only about which key we READ.
"""
import pytest

from dashboard.backend.integrations.news_sentiment import _project_entry

BASE = {"sentiment": "bullish", "rationale": "r", "headline": "h",
        "source": "Reuters", "url": "https://example.com/a",
        "published": 1783330000.0, "guid": "g1", "n_articles": 2}


def test_project_entry_reads_sentiment_score_v2():
    entry = _project_entry({**BASE, "sentiment_score": 0.5},
                           reference_ts=1783333600.0)
    assert entry["score"] == 0.5


def test_project_entry_rejects_v1_score_only():
    """The deleted fallback accepted this silently. The wire cannot produce it
    any more, so staying quiet here would mean a real producer break renders as
    a normal-looking sentiment number instead of a fault."""
    with pytest.raises(KeyError):
        _project_entry({**BASE, "score": -0.3}, reference_ts=1783333600.0)


def test_project_entry_raises_when_sentiment_score_absent():
    """Fail loud like every other required field: score=None would flow
    silently into the panel and into every backtest step."""
    with pytest.raises(KeyError):
        _project_entry(dict(BASE), reference_ts=1783333600.0)
