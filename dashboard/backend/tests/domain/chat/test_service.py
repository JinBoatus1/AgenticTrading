"""Characterization tests for the canonical agent-chat service (Phase 3D3A).

All provider calls are mocked; no real Anthropic request occurs.
"""

import asyncio
import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from dashboard.backend.domain.chat import service as chat_service
from dashboard.backend.domain.chat.service import (
    SYSTEM_PROMPT,
    chat_with_agent,
    conversation_history,
    extract_text,
    reset_agent_conversation,
)

_BACKEND = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _clear_history():
    conversation_history.clear()
    yield
    conversation_history.clear()


class _FakeMessages:
    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._response


def _text_response(text: str):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


def _install_client(monkeypatch, *, response=None, error=None):
    fake_messages = _FakeMessages(response=response, error=error)
    monkeypatch.setattr(
        chat_service, "claude_client", SimpleNamespace(messages=fake_messages)
    )
    return fake_messages


# ---------------------------------------------------------------------------
# extract_text
# ---------------------------------------------------------------------------

def test_extract_text_joins_text_blocks_and_strips():
    resp = SimpleNamespace(content=[
        SimpleNamespace(type="text", text="hello"),
        SimpleNamespace(type="tool_use", text="ignored"),
        SimpleNamespace(type="text", text="world "),
    ])
    assert extract_text(resp) == "hello\nworld"


# ---------------------------------------------------------------------------
# chat_with_agent: request construction + history
# ---------------------------------------------------------------------------

def test_chat_constructs_request_and_records_history(monkeypatch):
    fake = _install_client(monkeypatch, response=_text_response("hi there"))

    answer = asyncio.run(chat_with_agent(user_id="u1", agent_id="a1", message="  hello  "))

    assert answer == "hi there"
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["model"] == chat_service.ANTHROPIC_MODEL
    assert call["max_tokens"] == 1200
    assert call["system"] == SYSTEM_PROMPT
    # history passed by reference; user message cleaned (stripped)
    history = conversation_history[("u1", "a1")]
    assert history[0] == {"role": "user", "content": "hello"}
    assert history[1] == {"role": "assistant", "content": "hi there"}


def test_chat_empty_message_raises_value_error(monkeypatch):
    _install_client(monkeypatch, response=_text_response("never"))
    with pytest.raises(ValueError, match="Message cannot be empty."):
        asyncio.run(chat_with_agent(user_id="u1", agent_id="a1", message="   "))


def test_chat_empty_answer_fallback(monkeypatch):
    _install_client(monkeypatch, response=_text_response("   "))
    answer = asyncio.run(chat_with_agent(user_id="u1", agent_id="a1", message="hello"))
    assert answer == "Claude returned an empty response."
    history = conversation_history[("u1", "a1")]
    assert history[-1] == {"role": "assistant", "content": "Claude returned an empty response."}


def test_chat_provider_error_propagates_and_pops_user_message(monkeypatch):
    boom = RuntimeError("provider down")
    _install_client(monkeypatch, error=boom)

    with pytest.raises(RuntimeError, match="provider down"):
        asyncio.run(chat_with_agent(user_id="u1", agent_id="a1", message="hello"))

    # The unanswered user message must not be retained.
    assert conversation_history[("u1", "a1")] == []


def test_chat_history_trimmed_to_12(monkeypatch):
    _install_client(monkeypatch, response=_text_response("ok"))
    key = ("u1", "a1")
    # Pre-fill with 12 messages so the new exchange forces trimming.
    conversation_history[key] = [
        {"role": "assistant", "content": f"m{i}"} for i in range(12)
    ]
    asyncio.run(chat_with_agent(user_id="u1", agent_id="a1", message="hello"))
    assert len(conversation_history[key]) == 12
    assert conversation_history[key][-1] == {"role": "assistant", "content": "ok"}


def test_sessions_are_keyed_by_user_and_agent(monkeypatch):
    _install_client(monkeypatch, response=_text_response("a"))
    asyncio.run(chat_with_agent(user_id="u1", agent_id="a1", message="hi"))
    asyncio.run(chat_with_agent(user_id="u2", agent_id="a1", message="hi"))
    assert ("u1", "a1") in conversation_history
    assert ("u2", "a1") in conversation_history
    assert conversation_history[("u1", "a1")] is not conversation_history[("u2", "a1")]


def test_reset_clears_only_that_session(monkeypatch):
    _install_client(monkeypatch, response=_text_response("a"))
    asyncio.run(chat_with_agent(user_id="u1", agent_id="a1", message="hi"))
    asyncio.run(chat_with_agent(user_id="u2", agent_id="a1", message="hi"))
    reset_agent_conversation(user_id="u1", agent_id="a1")
    assert ("u1", "a1") not in conversation_history
    assert ("u2", "a1") in conversation_history


# ---------------------------------------------------------------------------
# Prompt preservation
# ---------------------------------------------------------------------------

def test_system_prompt_exact():
    assert SYSTEM_PROMPT.startswith("You are the conversational assistant for Agentic Trading Lab.")
    assert SYSTEM_PROMPT.endswith(
        "general information from personalized financial advice."
    )
    assert "This Discord integration is currently an early chat prototype." in SYSTEM_PROMPT
    # .strip() applied at definition: no leading/trailing whitespace.
    assert SYSTEM_PROMPT == SYSTEM_PROMPT.strip()


# ---------------------------------------------------------------------------
# Compatibility identity
# ---------------------------------------------------------------------------

def test_shim_reexports_same_objects():
    import dashboard.backend.services.agent_chat_service as shim

    assert shim.chat_with_agent is chat_with_agent
    assert shim.reset_agent_conversation is reset_agent_conversation
    assert shim.conversation_history is conversation_history
    assert shim.SYSTEM_PROMPT is SYSTEM_PROMPT
    assert shim.claude_client is chat_service.claude_client


# ---------------------------------------------------------------------------
# Import boundaries
# ---------------------------------------------------------------------------

def _imported_modules(path: Path):
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
    return modules


def test_canonical_service_has_no_forbidden_imports():
    mods = _imported_modules(_BACKEND / "domain" / "chat" / "service.py")
    for m in mods:
        assert not m.startswith("dashboard.backend.api"), m
        assert m != "dashboard.backend.app", m
        assert not m.startswith("dashboard.scripts"), m
        assert "frontend" not in m, m


def test_discord_consumer_uses_canonical_path():
    mods = _imported_modules(_BACKEND / "integrations" / "discord_bot.py")
    assert "dashboard.backend.domain.chat.service" in mods
    assert "backend.services.agent_chat_service" not in mods
