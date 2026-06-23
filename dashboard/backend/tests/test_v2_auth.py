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
