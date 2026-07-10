"""Tests for Discord persistence store."""

import tempfile
from pathlib import Path

from dashboard.backend.integrations.discord_store import DiscordStore


def test_connect_and_confirm_link():
    with tempfile.TemporaryDirectory() as tmp:
        store = DiscordStore(db_path=Path(tmp) / "discord.db")
        tok = store.create_connect_token(
            discord_user_id="111",
            discord_username="tester",
        )
        assert tok["linked"] is False
        assert tok["code"]

        assert not store.is_linked("111")

        store.confirm_link(link_code=tok["code"], atl_user_id=42)
        assert store.is_linked("111")
        assert store.atl_user_id_for("111") == 42

        again = store.create_connect_token(discord_user_id="111")
        assert again["linked"] is True
        assert again["atl_user_id"] == 42


def test_dm_session_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        store = DiscordStore(db_path=Path(tmp) / "discord.db")
        store.confirm_link(
            link_code=store.create_connect_token(discord_user_id="222")["code"],
            atl_user_id=7,
        )
        session = store.get_or_create_session(discord_user_id="222", atl_user_id=7)
        assert session["discord_user_id"] == "222"

        updated = store.update_session(
            "222",
            selected_agent_id="agent_abc",
            pending_backtest={"symbols": ["AAPL"]},
        )
        assert updated["selected_agent_id"] == "agent_abc"
        pending = store.get_pending_backtest("222")
        assert pending["symbols"] == ["AAPL"]

        store.update_session("222", clear_pending=True)
        assert store.get_pending_backtest("222") is None
