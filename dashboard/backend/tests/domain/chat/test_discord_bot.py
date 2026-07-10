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


def test_command_names_and_registration():
    names = {cmd.name for cmd in bot_mod.bot.tree.get_commands()}
    assert {"reset", "agent", "backtest", "strategy", "atl"} <= names
    assert "ask" not in names


def test_bot_prefix_and_message_content_intent():
    assert bot_mod.bot.command_prefix == "!"
    expected = discord.Intents.default()
    expected.message_content = True
    assert bot_mod.bot.intents.value == expected.value


def test_dm_welcome_copy():
    assert "private" in bot_mod.DM_WELCOME.lower() or "dm" in bot_mod.DM_WELCOME.lower()
    assert "backtest" in bot_mod.DM_WELCOME.lower()
    assert "/atl" in bot_mod.DM_WELCOME or "show my agents" in bot_mod.DM_WELCOME


def test_agent_status_line_none_selected():
    bot_mod._selected_agents.clear()
    line = bot_mod.agent_status_line("user-1")
    assert "none selected" in line
    assert "/agent" in line


def test_agent_status_line_shows_selection():
    bot_mod._selected_agents["user-1"] = {
        "agent_id": "abc",
        "name": "Haiku Trader",
        "model_name": "claude-haiku-4-5-20251001",
    }
    line = bot_mod.agent_status_line("user-1")
    assert "Haiku Trader" in line
    assert "claude-haiku" in line
    bot_mod._selected_agents.clear()


def test_interaction_ephemeral_visible_in_guild_only():
    class _GuildChannel:
        pass

    interaction = type("I", (), {"channel": _GuildChannel()})()
    assert bot_mod.interaction_ephemeral(interaction) is True


def test_chat_user_id_isolates_dm_and_guild():
    dm = bot_mod.chat_user_id("42", is_dm=True)
    guild = bot_mod.chat_user_id("42", is_dm=False)
    assert dm != guild
    assert dm == "discord:dm:42"
    assert guild == "discord:guild:42"


def test_detect_backtest_intent():
    assert bot_mod.detect_backtest_intent("let's run backtest")
    assert bot_mod.detect_backtest_intent("回测")
    assert not bot_mod.detect_backtest_intent("what is a backtest?")


def test_parse_text_slash_command():
    assert bot_mod.parse_text_slash_command("/agent") == ("agent", "")
    assert bot_mod.parse_text_slash_command("/backtest momentum") == (
        "backtest",
        "momentum",
    )
    assert bot_mod.parse_text_slash_command("hello") is None
    assert bot_mod.parse_text_slash_command("/unknown") is None

    assert bot_mod.is_backtest_confirmation("yes")
    assert bot_mod.is_backtest_confirmation("确认")
    assert bot_mod.is_backtest_cancellation("cancel")
    assert bot_mod.is_backtest_cancellation("取消")


def test_should_handle_free_chat():
    assert bot_mod.should_handle_free_chat(
        author_is_bot=False,
        content="hello",
        is_dm=True,
        channel_id=1,
        mentions_bot=False,
        is_reply_to_bot=False,
    )
    assert not bot_mod.should_handle_free_chat(
        author_is_bot=True,
        content="hello",
        is_dm=True,
        channel_id=1,
        mentions_bot=False,
        is_reply_to_bot=False,
    )
    assert not bot_mod.should_handle_free_chat(
        author_is_bot=False,
        content="",
        is_dm=False,
        channel_id=1,
        mentions_bot=False,
        is_reply_to_bot=False,
    )
    assert bot_mod.should_handle_free_chat(
        author_is_bot=False,
        content="",
        is_dm=False,
        channel_id=1,
        mentions_bot=True,
        is_reply_to_bot=False,
    )
    assert bot_mod.should_handle_free_chat(
        author_is_bot=False,
        content="hi",
        is_dm=False,
        channel_id=99,
        mentions_bot=True,
        is_reply_to_bot=False,
    )


def test_extract_chat_prompt_strips_mention():
    assert bot_mod.extract_chat_prompt(
        "<@123456789> what is momentum?",
        bot_user_id=123456789,
    ) == "what is momentum?"


def test_model_override_maps_sentinel_to_none():
    # H7: a selected agent's default 'local-model' sentinel means "no override".
    assert bot_mod._model_override("local-model") is None
    assert bot_mod._model_override("rule-based") is None
    assert bot_mod._model_override(None) is None
    # A real model id passes through unchanged.
    assert bot_mod._model_override("claude-haiku-4-5-20251001") == "claude-haiku-4-5-20251001"


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
