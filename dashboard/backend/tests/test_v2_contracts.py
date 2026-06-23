import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from api.v2.models import (  # noqa: E402
    SCHEMA_VERSION, UNIVERSE, ActionItem, ContextEnvelope,
    DecisionRequest, ErrorEnvelope, NewsSentimentEntry, SubmitAck,
)


def test_schema_version_and_universe():
    assert SCHEMA_VERSION == "2.0"
    assert "AAPL" in UNIVERSE and len(UNIVERSE) == 30


def test_news_sentiment_entry_rejects_out_of_range_score():
    with pytest.raises(ValidationError):
        NewsSentimentEntry(sentiment="bullish", score=1.5, headline="x",
                           source="Reuters", url="http://x", age_hours=1.0, n_articles=1)


def test_action_item_rejects_off_universe_symbol():
    with pytest.raises(ValidationError):
        ActionItem(action="buy", symbol="ZZZ", confidence=0.5,
                   reasoning="valid reason", position_size=10)


def test_action_item_rejects_bad_confidence():
    with pytest.raises(ValidationError):
        ActionItem(action="buy", symbol="AAPL", confidence=2.0,
                   reasoning="valid reason", position_size=10)


def test_decision_request_requires_idempotency_key():
    with pytest.raises(ValidationError):
        DecisionRequest(actions=[])


def test_context_envelope_defaults_news_slot_present():
    env = ContextEnvelope(
        schema_version=SCHEMA_VERSION, run_id="run_1", mode="backtest",
        step_index=0, total_steps=10, loop="lockstep", status="loading",
        universe=UNIVERSE,
    )
    assert env.news_sentiment == {}
    assert env.news_overview is None


def test_submit_ack_minimal_valid():
    ack = SubmitAck(accepted=True, decision_source="external_agent",
                    status="waiting_decision", run_id="run_1")
    assert ack.executed == [] and ack.rejected == []


def test_error_envelope_shape():
    err = ErrorEnvelope.model_validate({"error": {
        "code": "validation_failed", "message": "bad", "retryable": False}})
    assert err.error.code == "validation_failed"
