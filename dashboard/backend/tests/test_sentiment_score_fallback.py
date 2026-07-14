"""PR-1 of the FinSearch score-field disambiguation (see FinSearch spec
2026-07-14-score-field-disambiguation-design.md): _project_entry must read
sentiment_score (signals v2) and fall back to score (v1) until PR-2 deletes
the fallback."""
from dashboard.backend.integrations.news_sentiment import _project_entry

BASE = {"sentiment": "bullish", "rationale": "r", "headline": "h",
        "source": "Reuters", "url": "https://example.com/a",
        "published": 1783330000.0, "guid": "g1", "n_articles": 2}


def test_project_entry_reads_sentiment_score_v2():
    entry = _project_entry({**BASE, "sentiment_score": 0.5},
                           reference_ts=1783333600.0)
    assert entry["score"] == 0.5


def test_project_entry_falls_back_to_v1_score():
    entry = _project_entry({**BASE, "score": -0.3},
                           reference_ts=1783333600.0)
    assert entry["score"] == -0.3


def test_project_entry_prefers_sentiment_score_when_both_present():
    entry = _project_entry({**BASE, "sentiment_score": 0.5, "score": -0.9},
                           reference_ts=1783333600.0)
    assert entry["score"] == 0.5
