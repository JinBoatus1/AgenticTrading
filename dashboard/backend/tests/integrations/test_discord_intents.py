"""Tests for Discord DM intent routing."""

from datetime import date

from dashboard.backend.integrations.discord_intents import (
    INTENT_HELP,
    INTENT_RUN_BACKTEST,
    INTENT_SHOW_AGENTS,
    INTENT_SELECT_AGENT,
    INTENT_CHECK_STATUS,
    parse_backtest_config,
    parse_date_range,
    parse_symbols,
    route_intent,
)


def test_route_show_agents():
    r = route_intent("show my agents")
    assert r.intent == INTENT_SHOW_AGENTS


def test_route_select_agent():
    r = route_intent("use momentum agent")
    assert r.intent == INTENT_SELECT_AGENT
    assert r.agent_query == "momentum"


def test_route_backtest():
    r = route_intent("run backtest on AAPL MSFT last month")
    assert r.intent == INTENT_RUN_BACKTEST
    assert "AAPL" in r.backtest["symbols"]
    assert r.backtest["start_date"] is not None


def test_route_status_and_help():
    assert route_intent("status").intent == INTENT_CHECK_STATUS
    assert route_intent("help").intent == INTENT_HELP


def test_route_connect():
    from dashboard.backend.integrations.discord_intents import INTENT_CONNECT

    assert route_intent("connect").intent == INTENT_CONNECT
    assert route_intent("I want to connect").intent == INTENT_CONNECT
    assert route_intent("link my account").intent == INTENT_CONNECT


def test_parse_mag7():
    assert parse_symbols("Magnificent 7 backtest") == [
        "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META",
    ]


def test_parse_last_month():
    start, end = parse_date_range("last month", today=date(2026, 7, 10))
    assert start == "2026-06-01"
    assert end == "2026-06-30"


def test_parse_backtest_config():
    cfg = parse_backtest_config("run backtest on AAPL from 2026-05-01 to 2026-05-07")
    assert cfg["symbols"] == ["AAPL"]
    assert cfg["start_date"] == "2026-05-01"
    assert cfg["end_date"] == "2026-05-07"
