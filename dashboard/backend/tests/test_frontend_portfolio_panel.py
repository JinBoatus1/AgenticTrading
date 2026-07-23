"""Portfolio panel behaviour for the vanilla-JS dashboard (#175).

The frontend has no JS test harness, so -- following test_frontend_xss_guards.py
-- these run the *real* functions lifted out of ``js/portfolio.js`` under node.
The extraction is brace-matched against the shipped source, so renaming or
deleting a function breaks these tests instead of silently passing against a
stale copy.

Two contracts are covered:

1. A live (signed-in) portfolio must not render fabricated P/L. The ledger
   tracks cash only, so a "$0.00" P&L would be a made-up flat day presented
   as real data next to genuine figures — the overview card shows "—" instead.
2. Concurrent renders must not repaint out of order. Two are routinely in
   flight (the My Agents tab switch, then loadAgents), and responses are not
   guaranteed to land in request order.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

_PORTFOLIO_JS = (
    Path(__file__).resolve().parents[2] / "frontend" / "js" / "portfolio.js"
)

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node is not installed"
)


def _extract_function(src: str, name: str) -> str:
    """Return the source of ``[async ]function <name>(...) { ... }``."""
    for marker in (f"async function {name}(", f"function {name}("):
        start = src.find(marker)
        if start != -1:
            break
    else:  # pragma: no cover - only trips if the function was renamed
        raise AssertionError(f"{name} not found in {_PORTFOLIO_JS.name}")
    depth = 0
    i = src.index("{", start)
    while True:
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start : i + 1]
        i += 1


def _run_node(script: str):
    result = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


_OVERVIEW_HARNESS = [
    # Minimal DOM + formatting stubs; everything under test is the real source.
    "const pfMoney = (v) => `$${Number(v).toFixed(2)}`;",
    "const PF_WALLET_ICON = '';",
    "const root = { innerHTML: '' };",
    "const document = { getElementById: () => root };",
]


def test_live_portfolio_reports_pnl_as_unavailable_not_zero():
    src = _PORTFOLIO_JS.read_text(encoding="utf-8")
    script = "\n".join(
        _OVERVIEW_HARNESS
        + [
            _extract_function(src, "portfolioPct"),
            _extract_function(src, "normalizeSummary"),
            _extract_function(src, "summaryFromLivePortfolio"),
            _extract_function(src, "renderPortfolioOverview"),
            "renderPortfolioOverview(summaryFromLivePortfolio(",
            "  { equity: 10000, cash_available: 7500, allocated: 2500 }));",
            "console.log(JSON.stringify(root.innerHTML));",
        ]
    )
    html = _run_node(script)

    # The P&L slot shows an em dash, never a fabricated flat "$0.00" day.
    assert "—" in html
    assert "$0.00" not in html
    # Real figures still render normally.
    assert "$10000.00" in html
    assert "$7500.00" in html
    assert "$2500.00" in html


def test_mock_portfolio_still_renders_its_pnl():
    """The guard must key on the live flag, not blank the sample data too."""
    src = _PORTFOLIO_JS.read_text(encoding="utf-8")
    script = "\n".join(
        _OVERVIEW_HARNESS
        + [
            _extract_function(src, "portfolioPct"),
            _extract_function(src, "normalizeSummary"),
            _extract_function(src, "renderPortfolioOverview"),
            "renderPortfolioOverview(",
            "  { totalValue: 10000, cashAvailable: 2000, allocated: 8000 });",
            "console.log(JSON.stringify(root.innerHTML));",
        ]
    )
    html = _run_node(script)

    # Sample data keeps its placeholder P&L rather than the live-only dash.
    assert "$0.00" in html
    assert "—" not in html


def test_a_slow_earlier_render_cannot_repaint_over_a_newer_one():
    """Request 1 resolves *after* request 2; only request 2 may paint."""
    src = _PORTFOLIO_JS.read_text(encoding="utf-8")
    script = "\n".join(
        [
            "let portfolioRenderSeq = 0;",
            "const painted = [];",
            "const API_BASE = '';",
            "const isPortfolioSignedIn = () => true;",
            "const renderPortfolioFromMock = () => painted.push('mock');",
            "const renderPortfolioFromLive = (p) => painted.push(p.tag);",
            # First call hangs for 50ms, second returns immediately.
            "let call = 0;",
            "const API = { get: () => {",
            "  call += 1;",
            "  const tag = call === 1 ? 'stale' : 'fresh';",
            "  const delay = call === 1 ? 50 : 0;",
            "  return new Promise((r) => setTimeout(",
            "    () => r({ portfolio: { tag } }), delay));",
            "} };",
            _extract_function(src, "renderPortfolio"),
            "(async () => {",
            "  const first = renderPortfolio([]);",
            "  const second = renderPortfolio([]);",
            "  await Promise.all([first, second]);",
            "  console.log(JSON.stringify(painted));",
            "})();",
        ]
    )
    painted = _run_node(script)

    assert painted == ["fresh"], painted
