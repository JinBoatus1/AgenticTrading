"""MEDIUM #4 — POST /api/strategies must bound prompt size and write rate.

The endpoint is public by design (shared links work without a session), but it
had no prompt size cap and no write rate limit — an anonymous client could write
unbounded, megabyte-sized prompts without any throttle. These tests pin the size
cap (422) and a per-client write rate limit (429). ``owner`` remains a
display-only attribution label (e.g. ``discord:<id>``), never an auth control.
"""

import pytest
from fastapi.testclient import TestClient

from dashboard.backend.app import app
from dashboard.backend.api.rate_limit import FixedWindowRateLimiter
import dashboard.backend.api.routers.strategies as strategies_router


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    # Guarded so the pure-limiter unit tests below pass even before the endpoint
    # is wired to a module-level limiter (clean red-green).
    rl = getattr(strategies_router, "_create_rate_limiter", None)
    if rl is not None:
        rl.reset()
    yield
    rl = getattr(strategies_router, "_create_rate_limiter", None)
    if rl is not None:
        rl.reset()


# --- FixedWindowRateLimiter unit tests (deterministic fake clock) -----------

def test_rate_limiter_allows_up_to_max_then_rejects():
    now = [0.0]
    rl = FixedWindowRateLimiter(max_events=2, window_seconds=10, clock=lambda: now[0])
    assert rl.allow("k") is True
    assert rl.allow("k") is True
    assert rl.allow("k") is False  # 3rd within window


def test_rate_limiter_window_expiry_allows_again():
    now = [0.0]
    rl = FixedWindowRateLimiter(max_events=1, window_seconds=10, clock=lambda: now[0])
    assert rl.allow("k") is True
    assert rl.allow("k") is False
    now[0] = 11.0  # past the window
    assert rl.allow("k") is True


def test_rate_limiter_keys_are_independent():
    now = [0.0]
    rl = FixedWindowRateLimiter(max_events=1, window_seconds=10, clock=lambda: now[0])
    assert rl.allow("a") is True
    assert rl.allow("b") is True  # different key, own budget
    assert rl.allow("a") is False


# --- endpoint tests ---------------------------------------------------------

def test_create_strategy_ok_returns_share_url():
    client = TestClient(app)
    resp = client.post("/api/strategies", json={"prompt": "buy the dip"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"]
    assert body["share_url"].endswith(f"/strategy?code={body['code']}")


def test_create_strategy_rejects_oversized_prompt():
    client = TestClient(app)
    resp = client.post("/api/strategies", json={"prompt": "x" * 6000})
    assert resp.status_code == 422


def test_create_strategy_rate_limited_per_client(monkeypatch):
    # Swap in a tiny limiter so we don't need 30 real DB writes to prove wiring.
    now = [0.0]
    monkeypatch.setattr(
        strategies_router,
        "_create_rate_limiter",
        FixedWindowRateLimiter(max_events=2, window_seconds=3600, clock=lambda: now[0]),
    )
    client = TestClient(app)
    headers = {"X-Session-Id": "rate-key-1"}
    assert client.post("/api/strategies", json={"prompt": "a"}, headers=headers).status_code == 200
    assert client.post("/api/strategies", json={"prompt": "b"}, headers=headers).status_code == 200
    third = client.post("/api/strategies", json={"prompt": "c"}, headers=headers)
    assert third.status_code == 429
