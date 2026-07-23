"""Portfolio panel behaviour for the vanilla-JS dashboard (#175).

The frontend has no JS test harness, so -- following test_frontend_xss_guards.py
-- these run the *real* functions lifted out of ``js/portfolio.js`` under node.
The extraction is brace-matched against the shipped source, so renaming or
deleting a function breaks these tests instead of silently passing against a
stale copy.

Two contracts are covered:

1. A live (signed-in) portfolio must not render fabricated P/L. The ledger
   tracks cash only, so "+$0.00 (0.00%)" would be a made-up flat day presented
   as real data next to genuine figures.
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


def test_live_portfolio_reports_pnl_as_unavailable_not_zero():
    src = _PORTFOLIO_JS.read_text(encoding="utf-8")
    script = "\n".join(
        [
            "const pfMoney = (v) => `$${Number(v).toFixed(2)}`;",
            "const pfSignedMoney = (v) => `${Number(v) >= 0 ? '+' : ''}$${Number(v).toFixed(2)}`;",
            "const pfSignedPct = (v) => `${Number(v) >= 0 ? '+' : ''}${Number(v).toFixed(2)}%`;",
            _extract_function(src, "summaryFromLivePortfolio"),
            _extract_function(src, "buildSummaryCards"),
            "const cards = buildSummaryCards(summaryFromLivePortfolio(",
            "  { equity: 10000, cash_available: 7500, allocated: 2500 }));",
            "console.log(JSON.stringify(cards));",
        ]
    )
    cards = _run_node(script)

    by_label = {c["label"]: c for c in cards}
    assert by_label["Day P/L"]["value"] == "—"
    assert by_label["Total Return"]["value"] == "—"
    # Real figures still render normally.
    assert by_label["Total Portfolio Value"]["value"] == "$10000.00"
    assert by_label["Cash Available"]["value"] == "$7500.00"
    # Nothing anywhere on the cards claims a zero move.
    blob = json.dumps(cards)
    assert "0.00%" not in blob
    assert "+$0.00" not in blob


def test_mock_portfolio_still_renders_its_pnl():
    """The guard must key on the live flag, not blank the sample data too."""
    src = _PORTFOLIO_JS.read_text(encoding="utf-8")
    script = "\n".join(
        [
            "const pfMoney = (v) => `$${Number(v).toFixed(2)}`;",
            "const pfSignedMoney = (v) => `${Number(v) >= 0 ? '+' : ''}$${Number(v).toFixed(2)}`;",
            "const pfSignedPct = (v) => `${Number(v) >= 0 ? '+' : ''}${Number(v).toFixed(2)}%`;",
            _extract_function(src, "buildSummaryCards"),
            "console.log(JSON.stringify(buildSummaryCards(",
            "  { totalValue: 100, dayPnl: 5, dayPnlPct: 5, totalReturn: 9,",
            "    totalReturnPct: 9, cashAvailable: 20 })));",
        ]
    )
    by_label = {c["label"]: c for c in _run_node(script)}

    assert by_label["Day P/L"]["value"] == "+$5.00"
    assert by_label["Total Return"]["value"] == "+$9.00"


def test_a_slow_earlier_render_cannot_repaint_over_a_newer_one():
    """Request 1 resolves *after* request 2; only request 2 may paint."""
    src = _PORTFOLIO_JS.read_text(encoding="utf-8")
    script = "\n".join(
        [
            "let portfolioRenderToken = 0;",
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
