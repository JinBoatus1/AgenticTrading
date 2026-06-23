"""Focused tests for Discord integration import-safety (Phase 3D3B).

These require the optional ``discord`` dependency; when it is absent the whole
module is skipped so the suite stays green on minimal interpreters. No real
Discord connection or network call is made.
"""

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

discord = pytest.importorskip("discord")

import dashboard.backend.integrations.discord_bot as bot_mod

_BACKEND = Path(__file__).resolve().parents[3]
_REPO_ROOT = _BACKEND.parents[1]


def test_default_agent_id_unchanged():
    assert bot_mod.DEFAULT_AGENT_ID == "default"


def test_command_names_and_registration_unchanged():
    names = {cmd.name for cmd in bot_mod.bot.tree.get_commands()}
    assert {"ask", "reset", "agent"} <= names


def test_bot_prefix_and_intents_unchanged():
    assert bot_mod.bot.command_prefix == "!"
    assert bot_mod.bot.intents.value == discord.Intents.default().value


def test_consumes_canonical_chat_service():
    # The bot must call the canonical chat boundary, not Anthropic directly.
    from dashboard.backend.domain.chat.service import (
        chat_with_agent,
        reset_agent_conversation,
    )

    assert bot_mod.chat_with_agent is chat_with_agent
    assert bot_mod.reset_agent_conversation is reset_agent_conversation


def test_split_discord_message_short_returns_single_chunk():
    assert bot_mod.split_discord_message("hello", limit=1800) == ["hello"]


def test_split_discord_message_splits_long_text():
    text = "\n".join(f"line {i}" for i in range(500))
    chunks = bot_mod.split_discord_message(text, limit=100)
    assert len(chunks) > 1
    assert all(len(chunk) <= 100 for chunk in chunks)


def test_discord_bot_imports_without_secrets():
    code = textwrap.dedent(
        """
        import os
        for var in (
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_MODEL",
            "DISCORD_BOT_TOKEN",
            "DISCORD_GUILD_ID",
        ):
            os.environ.pop(var, None)

        import dashboard.backend.domain.chat.service
        import dashboard.backend.integrations.discord_bot as bot_mod
        # Importing must not construct the Anthropic client nor connect Discord.
        assert dashboard.backend.domain.chat.service._claude_client is None
        assert not bot_mod.bot.is_ready()
        print("import-safe")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
    )
    assert result.returncode == 0, result.stderr
    assert "import-safe" in result.stdout
