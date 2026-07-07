"""Tests for Playground-aligned chart styling helpers."""

from dashboard.backend.chart_style import (
    PLAYGROUND_SERIES_COLORS,
    format_playground_timestamp,
    series_color,
    series_kind,
)


def test_series_kind_and_colors_match_playground():
    assert series_kind("algo_123", "Agent") == "my-algo"
    assert series_kind("ext_abc", "My Bot") == "external-agent"
    assert series_kind("agent_123", "Agent") == "agent"
    assert series_kind("djia_index_1", "DJIA") == "djia"
    assert series_kind("buyhold_1", "buy-and-hold") == "buy-and-hold"

    assert series_color("agent_123", "Agent") == PLAYGROUND_SERIES_COLORS["agent"]
    assert series_color("buyhold_1", "buy-and-hold") == "#9AA4B2"
    assert series_color("djia_index_1", "DJIA") == "#F5C04A"


def test_format_playground_timestamp():
    from datetime import datetime

    assert format_playground_timestamp(datetime(2026, 5, 2, 14, 30)) == "May 2"
