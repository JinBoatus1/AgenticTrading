"""Source-level contract for the vanilla-JS market-data selector."""

from pathlib import Path


_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
_APP_HTML = _FRONTEND / "app.html"
_APP_JS = _FRONTEND / "app.js"


def test_market_data_controls_and_provenance_badge_exist():
    html = _APP_HTML.read_text(encoding="utf-8")

    assert 'id="marketDataSourceSelect"' in html
    assert 'value="alpaca"' in html
    assert 'value="vnpy_simulation"' not in html
    assert 'id="vnpySimulationNotice"' in html
    assert 'id="backtestDataSourceBadge"' in html


def test_vnpy_option_is_feature_gated_and_updates_model_state():
    source = _APP_JS.read_text(encoding="utf-8")

    assert "async function loadMarketDataFeatures(" in source
    assert "features.vnpy_simulation_enabled === true" in source
    assert "option.value = 'vnpy_simulation'" in source
    assert "modelSelect.disabled = isSimulation" in source


def test_backtest_request_and_result_labels_include_data_source():
    source = _APP_JS.read_text(encoding="utf-8")

    assert "data_source: dataSource" in source
    assert "renderBacktestDataSourceBadge(selectedRun)" in source
    assert "run.data_source === 'vnpy_simulation'" in source
    assert "vn.py simulated data" in source
