"""Static frontend route behavior served by the composition root.

MEDIUM #5 — ``GET /app/`` (trailing slash) previously served ``app.html``
directly. Because ``app.html`` references its assets with *relative* paths
(``styles.css``, ``app.js``, ``images/...``), the browser resolves them against
``/app/`` (e.g. ``/app/styles.css`` → 404) and the dashboard renders unstyled /
broken. The fix redirects ``/app/`` → ``/app`` so relative assets resolve
against root.
"""

from fastapi.testclient import TestClient

from dashboard.backend.app import app


def test_app_trailing_slash_redirects_to_app():
    """/app/ must 308-redirect to /app (method-preserving) so relative
    asset paths in app.html resolve against root rather than /app/."""
    client = TestClient(app)
    resp = client.get("/app/", follow_redirects=False)
    assert resp.status_code == 308
    assert resp.headers["location"] == "/app"


def test_app_trailing_slash_preserves_query_string():
    """The redirect must keep query params so deep-links (?auth=login, ?view=paper)
    survive the trailing-slash normalization."""
    client = TestClient(app)
    resp = client.get("/app/?auth=login&view=paper", follow_redirects=False)
    assert resp.status_code == 308
    assert resp.headers["location"] == "/app?auth=login&view=paper"


def test_app_serves_dashboard_html():
    """/app (no trailing slash) still serves the dashboard HTML directly."""
    client = TestClient(app)
    resp = client.get("/app")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
