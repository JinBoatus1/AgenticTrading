import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent_store import AgentStore  # noqa: E402


def _store(tmp_path):
    return AgentStore(db_path=tmp_path / "agents.db")


def test_new_agent_has_default_scopes(tmp_path):
    store = _store(tmp_path)
    agent = store.create_agent(name="scoped-agent", session_id=str(uuid.uuid4()))
    assert set(agent["scopes"]) == {
        "agents:register", "runs:write", "context:read",
        "decisions:write", "runs:read",
    }


def test_resolve_api_key_returns_scopes(tmp_path):
    store = _store(tmp_path)
    created = store.create_agent(name="scoped-agent", session_id=str(uuid.uuid4()))
    resolved = store.resolve_api_key(created["api_key"])
    assert resolved is not None
    assert "decisions:write" in resolved["scopes"]


import pytest  # noqa: E402

from api.v2.errors import ApiError  # noqa: E402
from auth_scopes import SCOPES, parse_scopes, require_scope  # noqa: E402


def test_scopes_constant_is_the_five():
    assert SCOPES == [
        "agents:register", "runs:write", "context:read",
        "decisions:write", "runs:read",
    ]


def test_parse_scopes_splits_and_strips():
    assert parse_scopes("runs:read, decisions:write ") == ["runs:read", "decisions:write"]


def test_require_scope_rejects_missing_key():
    dep = require_scope("runs:read")
    with pytest.raises(ApiError) as exc:
        dep(x_api_key=None)
    assert exc.value.status == 401
    assert exc.value.code == "unauthorized"


def test_require_scope_rejects_bad_scope(tmp_path, monkeypatch):
    import agent_store as agent_store_mod
    store = AgentStore(db_path=tmp_path / "a.db")
    created = store.create_agent(name="limited", session_id=str(uuid.uuid4()))
    # Narrow the agent's scopes so the requested one is absent
    conn = store._get_connection()
    conn.execute("UPDATE external_agents SET scopes = ? WHERE agent_id = ?",
                 ("runs:read", created["agent_id"]))
    conn.commit()
    conn.close()
    monkeypatch.setattr(agent_store_mod, "agent_store", store)
    import auth_scopes
    monkeypatch.setattr(auth_scopes, "agent_store", store)

    dep = require_scope("decisions:write")
    with pytest.raises(ApiError) as exc:
        dep(x_api_key=created["api_key"])
    assert exc.value.status == 403
    assert exc.value.code == "forbidden_scope"


from rate_limit import TokenBucketLimiter  # noqa: E402


def test_rate_limiter_allows_then_blocks():
    limiter = TokenBucketLimiter(per_minute=3, burst=3)
    results = [limiter.check("agent-1") for _ in range(4)]
    assert [r["allowed"] for r in results] == [True, True, True, False]
    assert results[-1]["remaining"] == 0
    assert results[-1]["retry_after"] >= 1


def test_rate_limiter_is_per_agent():
    limiter = TokenBucketLimiter(per_minute=1, burst=1)
    assert limiter.check("agent-a")["allowed"] is True
    assert limiter.check("agent-b")["allowed"] is True  # separate bucket
    assert limiter.check("agent-a")["allowed"] is False
