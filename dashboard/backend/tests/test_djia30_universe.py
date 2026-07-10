"""DJIA_30 single-source-of-truth guard (FinSearch↔ATL reconcile 2026-07-10).

validator.DJIA_30 is the one canonical Dow-30 for ATL: the backtest script and
the v2 API contract import it. (The docs example on origin/main is a MAG7 demo
with no Dow list — commit 13a2b64 — so there is nothing to guard there.)
Verified 2026-07-10 (S&P DJI, effective 2026-06-29).
"""
import ast
from pathlib import Path

from dashboard.backend.infrastructure.llm.validator import DJIA_30

_REPO = Path(__file__).resolve().parents[3]          # .../agent-trading-lab
_BHA = _REPO / "dashboard" / "scripts" / "backtest_hourly_agent.py"

EXPECTED = {
    "AAPL", "AMGN", "AMZN", "AXP", "BA", "CAT", "CRM", "CSCO", "CVX", "DIS",
    "GOOGL", "GS", "HD", "HON", "IBM", "JNJ", "JPM", "KO", "MCD", "MMM",
    "MRK", "MSFT", "NKE", "NVDA", "PG", "SHW", "TRV", "UNH", "V", "WMT",
}
FORBIDDEN = {"AMEX", "DOW", "INTC", "MA", "PFE", "WBA", "XOM", "VZ", "NFLX", "TSLA"}


def _module_djia30_literal(path):
    """The set in a top-level `DJIA_30 = [...]` literal, or None if the module
    has no such assignment (i.e. it imports the constant instead)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "DJIA_30":
                    return {ast.literal_eval(e) for e in node.value.elts}
    return None


def test_validator_is_the_current_index():
    assert set(DJIA_30) == EXPECTED
    assert len(DJIA_30) == 30
    assert len(set(DJIA_30)) == 30
    assert set(DJIA_30) & FORBIDDEN == set()


def test_backtest_script_imports_not_hardcodes():
    # After the fix there is no local DJIA_30 = [...] literal — it imports it.
    assert _module_djia30_literal(_BHA) is None


def test_api_universe_tracks_validator():
    from dashboard.backend.api.v2.models import UNIVERSE
    assert set(UNIVERSE) == EXPECTED
