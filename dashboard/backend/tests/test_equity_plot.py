"""Tests for gapless equity plot rendering."""

from datetime import datetime

import pytest
import pytz

from dashboard.backend.equity_plot import (
    compute_index_baseline_values,
    gapless_market_axis,
    render_backtest_equity_png,
)


def test_gapless_axis_advances_one_hour_per_market_bar():
    et = pytz.timezone("US/Eastern")
    fri = et.localize(datetime(2026, 5, 1, 10, 30))
    mon = et.localize(datetime(2026, 5, 4, 10, 30))
    x, ts_et = gapless_market_axis([fri, mon])
    assert len(x) == 2
    assert x[1] - x[0] == pytest.approx(1.0 / 24.0)
    assert ts_et[0].date().isoformat() == "2026-05-01"
    assert ts_et[1].date().isoformat() == "2026-05-04"


def test_compute_index_baseline_values_scales_to_initial_capital(monkeypatch):
    et = pytz.timezone("US/Eastern")
    t0 = et.localize(datetime(2026, 5, 1, 10, 30)).astimezone(pytz.UTC)
    t1 = et.localize(datetime(2026, 5, 1, 11, 30)).astimezone(pytz.UTC)

    monkeypatch.setattr(
        "dashboard.backend.equity_plot.fetch_index_hourly",
        lambda _sym, _start, _end: [(t0, 40_000.0), (t1, 41_000.0)],
    )

    values = compute_index_baseline_values(
        "^DJI",
        [t0, t1],
        "2026-05-01",
        "2026-05-01",
        100_000.0,
    )
    assert values == [100_000.0, pytest.approx(102_500.0)]


def test_render_backtest_equity_png_bytes():
    et = pytz.timezone("US/Eastern")
    stamps = [
        et.localize(datetime(2026, 5, 1, 10, 30)),
        et.localize(datetime(2026, 5, 1, 11, 30)),
        et.localize(datetime(2026, 5, 4, 10, 30)),
    ]
    png = render_backtest_equity_png(
        agent_label="Agent",
        agent_run_id="agent_test_1",
        timestamps=stamps,
        agent_values=[100_000, 100_500, 101_000],
        baselines=[
            ("DJIA index", "index:^DJI", [100_000, 99_800, 99_600]),
            ("Nasdaq-100", "index:^NDX", [100_000, 99_700, 99_400]),
        ],
    )
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
