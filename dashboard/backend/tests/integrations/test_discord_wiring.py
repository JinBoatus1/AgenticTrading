"""H7 — the Discord bot must not forward a sentinel model id.

``discord`` is an undeclared optional dep, so importing ``discord_bot`` isn't
possible in the base test env. These checks read the source directly (no import)
so the wiring is locked even where discord is absent — the behavioral test lives
in tests/domain/chat/test_discord_bot.py under ``importorskip('discord')``.
"""

from pathlib import Path

_DISCORD_BOT = (
    Path(__file__).resolve().parents[2] / "integrations" / "discord_bot.py"
)


def _source() -> str:
    return _DISCORD_BOT.read_text(encoding="utf-8")


def test_bot_uses_model_override_helper():
    src = _source()
    assert "from dashboard.backend.infrastructure.llm.token_cost import is_free_model" in src
    assert "def _model_override(" in src
    # Used at BOTH forwarding sites (/ask model= and /backtest payload["model"]).
    assert src.count("_model_override(") >= 3  # 1 definition + 2 call sites


def test_bot_no_longer_forwards_raw_sentinel_model():
    src = _source()
    # The old raw forwards that leaked the 'local-model' sentinel are gone.
    assert 'payload["model"] = selected["model_name"]' not in src
    assert "model = selected.get(\"model_name\") if selected else None" not in src
