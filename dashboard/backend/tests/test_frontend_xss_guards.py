"""XSS guards for the vanilla-JS dashboard (CodeQL js/xss-through-exception #1098).

``appendAlgoChatMessage`` renders into ``innerHTML`` so that ``**bold**`` markers
survive, and every one of its callers feeds it text the server controls: an
``err.message`` built from a backend ``detail`` / a backtest job's ``error``
string (which embeds the subprocess stderr tail, and therefore the user's own
team name), the raw LLM ``reply``, and the echoed ``team_name``. Unescaped, that
is a script-injection sink.

The frontend has no JS test harness, so these run the *real* functions lifted out
of ``app.js`` under node — the extraction is brace-matched against the shipped
source, so the tests break if the functions are renamed or deleted rather than
silently passing against a stale copy. A source-level guard backs them up for the
case where node is unavailable.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
_APP_JS = _FRONTEND / "app.js"
_LEADERBOARD_JS = _FRONTEND / "js" / "leaderboard.js"

# Payloads shaped like what actually reaches the chat bubble.
_ATTACKS = [
    "<img src=x onerror=alert(1)>",
    "Error: <script>alert(document.cookie)</script>",
    'Backtest failed (code 1): Traceback ... team "<svg onload=alert(1)>"',
]


def _extract_function(src: str, name: str) -> str:
    """Return the source of ``function <name>(...) { ... }`` by brace matching."""
    marker = f"function {name}("
    start = src.index(marker)
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


def _run_renderer(inputs: list[str], entry: str = "renderAlgoChatHtml") -> list[str]:
    """Execute the shipped escape+render functions in node against ``inputs``."""
    src = _APP_JS.read_text(encoding="utf-8")
    parts = [_extract_function(src, "escapeHtml")]
    if entry != "escapeHtml":
        parts.append(_extract_function(src, entry))
    driver = "\n".join(
        parts
        + [
            "const cases = JSON.parse(process.argv[1]);",
            f"console.log(JSON.stringify(cases.map({entry})));",
        ]
    )
    proc = subprocess.run(
        ["node", "-e", driver, json.dumps(inputs)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


requires_node = pytest.mark.skipif(
    shutil.which("node") is None, reason="node is required to execute app.js functions"
)


@requires_node
def test_chat_bubble_neutralizes_injected_markup():
    for attack, rendered in zip(_ATTACKS, _run_renderer(_ATTACKS)):
        assert "<img" not in rendered, attack
        assert "<script" not in rendered, attack
        assert "<svg" not in rendered, attack
        assert "&lt;" in rendered, attack


@requires_node
def test_chat_bubble_still_renders_bold_markers():
    # The escaping must not cost the one bit of markup the bubble deliberately
    # supports — otherwise the fix would be a regression the next dev reverts.
    assert _run_renderer(["Strategy updated: **4 blocks**"]) == [
        "Strategy updated: <strong>4 blocks</strong>"
    ]


@requires_node
def test_chat_bubble_escapes_quotes_and_ampersands():
    assert _run_renderer(['a & b "c"']) == ["a &amp; b &quot;c&quot;"]


@requires_node
def test_escape_html_neutralizes_markup():
    """``escapeHtml`` is the shared primitive behind all three error sinks."""
    assert _run_renderer(_ATTACKS, entry="escapeHtml") == [
        "&lt;img src=x onerror=alert(1)&gt;",
        "Error: &lt;script&gt;alert(document.cookie)&lt;/script&gt;",
        "Backtest failed (code 1): Traceback ... team "
        "&quot;&lt;svg onload=alert(1)&gt;&quot;",
    ]


def _inner_html_assignments(body: str) -> list[str]:
    return [ln.strip() for ln in body.splitlines() if "innerHTML" in ln and "=" in ln]


def test_paper_trading_error_escapes_the_exception_text():
    """``displayPaperError`` is fed ``error.message`` — same sink class as #1098."""
    body = _extract_function(_APP_JS.read_text(encoding="utf-8"), "displayPaperError")
    assignments = _inner_html_assignments(body)
    assert assignments
    for line in assignments:
        assert "escapeHtml(message)" in line, line


def test_leaderboard_error_escapes_the_exception_text():
    """``displayLeaderboardError`` is called with a bare ``error.message``."""
    src = _LEADERBOARD_JS.read_text(encoding="utf-8")
    body = _extract_function(src, "displayLeaderboardError")
    assignments = _inner_html_assignments(body)
    assert assignments
    for line in assignments:
        assert "escapeHtml(message)" in line, line


def test_chat_bubble_never_assigns_unescaped_text_to_inner_html():
    """Source guard: runs even where node is absent, so CI can never fail open."""
    src = _APP_JS.read_text(encoding="utf-8")
    body = _extract_function(src, "appendAlgoChatMessage")
    for line in body.splitlines():
        if "innerHTML" in line and "=" in line:
            assert "renderAlgoChatHtml(" in line, line.strip()
    # The pre-fix sink — raw text straight into innerHTML — must stay gone.
    assert "innerHTML = text.replace(" not in " ".join(src.split())
