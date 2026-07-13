from __future__ import annotations

import asyncio
import io
import os
import uuid
from pathlib import Path
from typing import Any, Optional

import discord
import requests
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from dashboard.backend.domain.chat.service import (
    chat_with_agent,
    reset_agent_conversation,
    synthesize_strategy_prompt,
)
from dashboard.backend.infrastructure.llm.token_cost import is_free_model


def _model_override(model_name: Optional[str]) -> Optional[str]:
    """Map a sentinel / rule-based model name (e.g. the default ``'local-model'``)
    to ``None`` so it is treated as "no explicit model" instead of being sent to
    the hosted-model API as a real model id. Real model ids pass through."""
    return None if is_free_model(model_name) else model_name


_env_path = Path(__file__).resolve().parents[2] / ".env"
if _env_path.exists():
    load_dotenv(_env_path)
load_dotenv()


def require_env(name: str) -> str:
    value = os.getenv(name)

    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")

    return value


# Fallback agent used until a Discord user selects a built-in agent via /agent.
DEFAULT_AGENT_ID = "default"

# Per-Discord-user selection of a built-in agent (in-memory MVP state).
# Key:   Discord user id (str)
# Value: {"agent_id", "name", "model_name", "session_id"}
_selected_agents: dict[str, dict[str, Any]] = {}


def selected_agent_for(user_id: str) -> Optional[dict[str, Any]]:
    """Return the built-in agent the Discord user last chose via /agent, if any."""
    return _selected_agents.get(str(user_id))

# Stable namespace so each Discord user maps to a fixed backtest session UUID
# (the /backtest routes require a valid UUID X-Session-Id).
_SESSION_NAMESPACE = uuid.UUID("8f1b2c3d-0000-4000-8000-a9b8c7d6e5f4")


def api_base() -> str:
    """Base URL of the running Agentic Trading Lab backend."""
    return os.getenv("ATL_API_BASE", "http://localhost:8000").rstrip("/")


def _parse_id_list(raw: Optional[str]) -> list[int]:
    """Parse a comma/space/semicolon-separated list of integer IDs."""
    if not raw:
        return []
    ids: list[int] = []
    for part in raw.replace(";", ",").replace(" ", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError:
            print(f"Discord: ignoring invalid ID '{part}'")
    return ids


def guild_ids() -> list[int]:
    """Guilds (servers) to sync slash commands to. Supports a comma-separated list."""
    ids = _parse_id_list(require_env("DISCORD_GUILD_ID"))
    if not ids:
        raise RuntimeError("DISCORD_GUILD_ID must contain at least one guild id")
    return ids


def allowed_channel_ids() -> set[int]:
    """Optional channel allowlist. When non-empty, the bot only responds in these channels."""
    return set(_parse_id_list(os.getenv("DISCORD_CHANNEL_ID")))


def session_for(user_id: str) -> str:
    """Deterministic per-user backtest session id (valid UUID)."""
    return str(uuid.uuid5(_SESSION_NAMESPACE, f"discord-user:{user_id}"))


_CHAT_FAILURE_MSG = (
    "The model request failed. Check the bot terminal and verify the "
    "Discord token, the hosted-model key (COMMONSTACK_API_KEY or "
    "ANTHROPIC_API_KEY), the model id, and the account balance."
)


def _free_chat_channel_allowed(channel_id: int) -> bool:
    """When ``DISCORD_CHANNEL_ID`` is set, plain messages in those channels trigger chat."""
    allowed = allowed_channel_ids()
    return bool(allowed) and channel_id in allowed


def should_handle_free_chat(
    *,
    author_is_bot: bool,
    content: str,
    is_dm: bool,
    channel_id: int,
    mentions_bot: bool,
    is_reply_to_bot: bool,
) -> bool:
    """Whether a normal (non-slash) message should invoke the chat agent.

    - DMs: any non-empty message (no ``/ask`` needed).
    - Guild, ``DISCORD_CHANNEL_ID`` set: any message in those channels.
    - Guild, no allowlist: only @mention or reply-to-bot.
    """
    if author_is_bot:
        return False
    if content.strip().startswith("!"):
        return False
    if is_dm:
        return bool(content.strip())
    # @mention / reply works even when content is empty (missing Message Content Intent).
    if mentions_bot or is_reply_to_bot:
        return True
    if _free_chat_channel_allowed(channel_id):
        return bool(content.strip())
    return False


def extract_chat_prompt(content: str, *, bot_user_id: Optional[int]) -> str:
    """Strip leading @bot mention so ``@MyBot hello`` becomes ``hello``."""
    text = content.strip()
    if bot_user_id is not None:
        text = text.replace(f"<@{bot_user_id}>", "").replace(f"<@!{bot_user_id}>", "")
    return text.strip()


def split_discord_message(
    text: str,
    limit: int = 1800,
) -> list[str]:
    """
    Split long model responses into Discord-safe chunks.
    """
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text

    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break

        split_at = remaining.rfind("\n", 0, limit)

        if split_at < limit // 2:
            split_at = remaining.rfind(" ", 0, limit)

        if split_at < limit // 2:
            split_at = limit

        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()

    return chunks


# ---------------------------------------------------------------------------
# Backend HTTP helpers (run in a thread so the event loop is not blocked)
# ---------------------------------------------------------------------------

def _http_post(path: str, *, json: dict[str, Any], headers: Optional[dict] = None, timeout: int = 30) -> dict:
    resp = requests.post(f"{api_base()}{path}", json=json, headers=headers or {}, timeout=timeout)
    resp.raise_for_status()
    return resp.json() if resp.content else {}


def _http_get(path: str, *, headers: Optional[dict] = None, timeout: int = 30) -> dict:
    resp = requests.get(f"{api_base()}{path}", headers=headers or {}, timeout=timeout)
    resp.raise_for_status()
    return resp.json() if resp.content else {}


def _http_get_bytes(path: str, *, headers: Optional[dict] = None, timeout: int = 60) -> bytes:
    resp = requests.get(f"{api_base()}{path}", headers=headers or {}, timeout=timeout)
    resp.raise_for_status()
    return resp.content


def _http_get_status(
    path: str,
    *,
    headers: Optional[dict] = None,
    timeout: int = 30,
) -> tuple[int, dict]:
    """GET that returns (status_code, json_body) without raising on 4xx."""
    resp = requests.get(f"{api_base()}{path}", headers=headers or {}, timeout=timeout)
    try:
        body = resp.json() if resp.content else {}
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    return resp.status_code, body


def bot_api_headers(discord_user_id: str) -> dict[str, str]:
    """Service headers for Discord → backend identity calls."""
    return {
        "X-Discord-Bot-Secret": (os.getenv("DISCORD_BOT_API_SECRET") or "").strip(),
        "X-Discord-User-Id": str(discord_user_id),
    }


async def api_post(path: str, *, json: dict[str, Any], headers: Optional[dict] = None, timeout: int = 30) -> dict:
    return await asyncio.to_thread(_http_post, path, json=json, headers=headers, timeout=timeout)


async def api_get(path: str, *, headers: Optional[dict] = None, timeout: int = 30) -> dict:
    return await asyncio.to_thread(_http_get, path, headers=headers, timeout=timeout)


async def api_get_bytes(path: str, *, headers: Optional[dict] = None, timeout: int = 60) -> bytes:
    return await asyncio.to_thread(_http_get_bytes, path, headers=headers, timeout=timeout)


async def fetch_owned_agents(
    discord_user_id: str,
) -> tuple[list[dict[str, Any]], Optional[str]]:
    """Fetch agents owned by the website account linked to this Discord user.

    Returns ``(agents, error_code)``. ``error_code`` is ``discord_not_linked``,
    ``fetch_failed``, or ``None`` on success.
    """
    status, data = await asyncio.to_thread(
        _http_get_status,
        "/api/v1/discord/agents",
        headers=bot_api_headers(discord_user_id),
    )
    if status == 404:
        detail = data.get("detail")
        code = None
        if isinstance(detail, dict):
            code = detail.get("code")
        if code == "discord_not_linked" or status == 404:
            return [], "discord_not_linked"
    if status >= 400:
        print(f"Discord owned-agents fetch failed: HTTP {status} {data!r}")
        return [], "fetch_failed"
    agents = data.get("agents", []) if isinstance(data, dict) else []
    return (agents if isinstance(agents, list) else []), None


async def deliver_agent_chat(
    discord_user_id: str,
    prompt: str,
) -> tuple[list[str], Optional[str]]:
    """Run the hosted-model chat path shared by ``/ask`` and free-form messages.

    Returns ``(response_chunks, error_message)``. On success ``error_message`` is
    ``None``; on failure ``response_chunks`` is empty.
    """
    selected = selected_agent_for(discord_user_id)
    agent_id = selected["agent_id"] if selected else DEFAULT_AGENT_ID
    model = _model_override(selected.get("model_name")) if selected else None

    try:
        answer = await chat_with_agent(
            user_id=discord_user_id,
            agent_id=agent_id,
            message=prompt,
            model=model,
        )
        return split_discord_message(answer), None
    except Exception as exc:
        print("Discord chat request failed:", repr(exc))
        return [], _CHAT_FAILURE_MSG


class AgentSelect(discord.ui.Select):
    """Dropdown letting a user pick one of their owned built-in agents."""

    def __init__(self, agents: list[dict[str, Any]]):
        options: list[discord.SelectOption] = []
        for agent in agents[:25]:  # Discord caps selects at 25 options.
            model = agent.get("model_name") or "local-model"
            run_count = agent.get("run_count") or 0
            agent_type = agent.get("agent_type") or "builtin"
            options.append(
                discord.SelectOption(
                    label=(agent.get("name") or "agent")[:100],
                    value=agent["agent_id"],
                    description=f"{agent_type} · {model} · {run_count} run(s)"[:100],
                )
            )
        super().__init__(
            placeholder="Choose one of your agents…",
            min_values=1,
            max_values=1,
            options=options,
        )
        self._agents = {agent["agent_id"]: agent for agent in agents}

    async def callback(self, interaction: discord.Interaction) -> None:
        agent = self._agents.get(self.values[0])
        if not agent:
            await interaction.response.edit_message(
                content="That agent is no longer available. Run `/agent` again.",
                view=None,
            )
            return

        _selected_agents[str(interaction.user.id)] = {
            "agent_id": agent["agent_id"],
            "name": agent.get("name") or "agent",
            "model_name": agent.get("model_name") or "local-model",
            "session_id": agent.get("session_id"),
            "agent_type": agent.get("agent_type") or "builtin",
        }

        await interaction.response.edit_message(
            content=(
                f"You're now chatting with **{agent.get('name')}** "
                f"(model `{agent.get('model_name') or 'local-model'}`).\n"
                "Message me directly (or use `/ask`) — `/backtest` to run a strategy; "
                "results show up on the agent's card on the website."
            ),
            view=None,
        )


class AgentSelectView(discord.ui.View):
    def __init__(self, agents: list[dict[str, Any]], *, timeout: float = 120):
        super().__init__(timeout=timeout)
        self.add_item(AgentSelect(agents))


class StrategyRunBacktestView(discord.ui.View):
    """One-click backtest after ``/strategy`` saves a prompt."""

    def __init__(self, *, discord_user_id: str, code: str, timeout: float = 600):
        super().__init__(timeout=timeout)
        self.discord_user_id = discord_user_id
        self.code = code

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if str(interaction.user.id) != self.discord_user_id:
            await interaction.response.send_message(
                "Only the person who ran `/strategy` can use this button.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Run backtest", style=discord.ButtonStyle.green)
    async def run_backtest_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
        self.stop()
        try:
            await interaction.message.edit(view=None)
        except Exception:
            pass
        await execute_backtest(
            interaction,
            self.discord_user_id,
            code=self.code,
        )


async def execute_backtest(
    interaction: discord.Interaction,
    discord_user_id: str,
    *,
    prompt: Optional[str] = None,
    code: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> None:
    """Shared backtest runner for ``/backtest`` and strategy buttons.

    The interaction must already be deferred.
    """
    selected = selected_agent_for(discord_user_id)
    session_id = session_for(discord_user_id)
    headers = {"X-Session-Id": session_id}

    share_url: Optional[str] = None
    label = "custom"
    if prompt and prompt.strip():
        strategy_prompt = prompt.strip()
    elif code:
        label = code
        try:
            record = await api_get(f"/api/strategies/{code}")
            strategy_prompt = record.get("prompt")
            share_url = record.get("share_url")
            if not strategy_prompt:
                raise ValueError("empty prompt")
        except Exception:
            await interaction.edit_original_response(
                content=(
                    f"No strategy found for code `{code}`. "
                    "Type a `prompt` directly or create one with `/strategy`."
                )
            )
            return
    else:
        await interaction.edit_original_response(
            content="Give me a strategy: type a `prompt` directly, or pass a saved `code`."
        )
        return

    payload: dict[str, Any] = {"strategy_prompt": strategy_prompt}
    if selected and (selected.get("agent_type") or "builtin") == "builtin":
        payload["agent_id"] = selected["agent_id"]
    model_override = _model_override(selected.get("model_name")) if selected else None
    if model_override:
        payload["model"] = model_override
    if start:
        payload["start_date"] = start
    if end:
        payload["end_date"] = end

    try:
        started = await api_post("/backtest/run", json=payload, headers=headers)
    except Exception as exc:
        print("Discord /backtest start failed:", repr(exc))
        await interaction.edit_original_response(
            content=f"Could not start the backtest. Is the backend running at `{api_base()}`?"
        )
        return

    if not started.get("success", True):
        await interaction.edit_original_response(
            content=f"Backtest not started: {started.get('error', 'unknown error')}"
        )
        return

    effective_session = started.get("session_id") or session_id
    headers = {"X-Session-Id": effective_session}

    await interaction.edit_original_response(
        content=(
            f"Backtest started (`{label}`) with real Alpaca bars + hosted model. "
            "Running… this can take a few minutes."
        )
    )

    max_polls = 130
    for i in range(max_polls):
        await asyncio.sleep(5)
        try:
            status = await api_get("/backtest/status", headers=headers)
        except Exception:
            continue

        if status.get("running"):
            if (i + 1) % 6 == 0:
                await interaction.edit_original_response(
                    content=f"Backtest running (`{label}`)… ({(i + 1) * 5}s elapsed)"
                )
            continue

        if status.get("error"):
            await interaction.edit_original_response(
                content=f"Backtest failed: {status['error'][:1500]}"
            )
            return

        if status.get("success") or status.get("runs_count"):
            break
    else:
        await interaction.edit_original_response(
            content=(
                "Backtest is taking longer than expected. "
                "Check results later on the dashboard."
            )
        )
        return

    try:
        m = await api_get("/runs/latest/metrics", headers=headers)
    except Exception:
        await interaction.edit_original_response(
            content="Backtest finished, but metrics could not be read. Check the dashboard."
        )
        return

    def pct(v: Any) -> str:
        return "—" if v is None else f"{float(v) * 100:.2f}%"

    def num(v: Any) -> str:
        return "—" if v is None else f"{float(v):.2f}"

    summary = (
        f"**Backtest complete** · `{label}`\n"
        f"Window: {m.get('start_date', '?')} → {m.get('end_date', '?')}  ·  "
        f"model: {m.get('llm_model', '?')}\n"
        f"Return: **{pct(m.get('total_return'))}**  ·  Sharpe: {num(m.get('sharpe_ratio'))}  ·  "
        f"Max DD: {pct(m.get('max_drawdown'))}  ·  Trades: {m.get('num_trades', 0)}\n"
        f"Final equity: ${float(m.get('final_equity') or 0):,.0f}"
    )
    if share_url:
        summary += f"\nView: {share_url}"
    if selected and selected.get("name"):
        summary += (
            f"\nSaved to **{selected['name']}**'s card — open *My Agents* on the "
            "website to track the details."
        )
    await interaction.edit_original_response(content=summary)

    run_id = m.get("run_id")
    if run_id:
        try:
            png = await api_get_bytes(f"/runs/{run_id}/plot.png", headers=headers)
            chart = discord.File(io.BytesIO(png), filename=f"backtest_{run_id}.png")
            await interaction.followup.send(file=chart, ephemeral=True)
        except Exception as exc:
            print("Discord /backtest plot failed:", repr(exc))


class RestrictedCommandTree(app_commands.CommandTree):
    """Command tree that optionally restricts commands to an allowlisted channel.

    When ``DISCORD_CHANNEL_ID`` is set (one or more ids), slash commands only run
    in those channels; elsewhere the user gets a short ephemeral notice. When it
    is unset, the bot responds in any channel.
    """

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        allowed = allowed_channel_ids()
        if allowed and interaction.channel_id not in allowed:
            try:
                await interaction.response.send_message(
                    "This bot only responds in its designated channel here. "
                    "Please use the configured channel.",
                    ephemeral=True,
                )
            except Exception:
                pass
            return False
        return True


class AgenticTradingDiscordBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(
            command_prefix="!",
            intents=intents,
            tree_cls=RestrictedCommandTree,
        )

    async def setup_hook(self) -> None:
        """
        Sync commands to each configured guild (server).

        Guild-level synchronization makes commands appear quickly. Supports a
        comma-separated ``DISCORD_GUILD_ID`` so the bot can serve multiple
        servers at once.
        """
        for guild_id in guild_ids():
            guild = discord.Object(id=guild_id)
            self.tree.copy_global_to(guild=guild)
            synced_commands = await self.tree.sync(guild=guild)
            print(
                f"Synced {len(synced_commands)} Discord command(s) "
                f"to guild {guild_id}."
            )

        allowed = allowed_channel_ids()
        if allowed:
            print(f"Command channel allowlist active: {sorted(allowed)}")
            print(
                "Free chat: plain messages in allowlisted channels (no /ask). "
                "Also: DMs, @mention, or reply-to-bot elsewhere."
            )
        else:
            print(
                "Free chat: DMs, @mention, or reply-to-bot. "
                "Set DISCORD_CHANNEL_ID for open chat in specific channels."
            )


bot = AgenticTradingDiscordBot()


@bot.event
async def on_ready() -> None:
    if bot.user is not None:
        print(f"Discord bot connected as {bot.user}.")
    print(
        "Reminder: server-channel free chat needs Message Content Intent enabled "
        "in the Discord Developer Portal (Bot → Privileged Gateway Intents). "
        "DMs work without it."
    )


@bot.event
async def on_message(message: discord.Message) -> None:
    """Free-form chat: DMs, allowlisted channels, @mention, or reply-to-bot."""
    bot_user = bot.user
    is_reply_to_bot = False
    if message.reference is not None:
        resolved = message.reference.resolved
        if isinstance(resolved, discord.Message) and bot_user is not None:
            is_reply_to_bot = resolved.author.id == bot_user.id

    mentions_bot = bool(bot_user and bot_user in message.mentions)
    is_dm = isinstance(message.channel, discord.DMChannel)

    if not should_handle_free_chat(
        author_is_bot=message.author.bot,
        content=message.content or "",
        is_dm=is_dm,
        channel_id=message.channel.id,
        mentions_bot=mentions_bot,
        is_reply_to_bot=is_reply_to_bot,
    ):
        await bot.process_commands(message)
        return

    prompt = extract_chat_prompt(
        message.content or "",
        bot_user_id=bot_user.id if bot_user else None,
    )
    if not prompt:
        if mentions_bot or is_reply_to_bot:
            raw = (message.content or "").strip()
            if not raw:
                await message.reply(
                    "I see the @mention, but Discord isn't sending me your message "
                    "text in this server. Enable **Message Content Intent** for this "
                    "bot in the [Developer Portal](https://discord.com/developers/applications) "
                    "→ Bot → Privileged Gateway Intents, then restart the bot. "
                    "Or **DM me** directly — that works without the intent.",
                    mention_author=False,
                )
            else:
                await message.reply(
                    "What would you like to ask? Include your question in the same "
                    "message as the @mention.",
                    mention_author=False,
                )
        await bot.process_commands(message)
        return

    discord_user_id = str(message.author.id)
    async with message.channel.typing():
        chunks, error = await deliver_agent_chat(discord_user_id, prompt)

    if error:
        await message.reply(error, mention_author=False)
    else:
        await message.reply(chunks[0], mention_author=False)
        for chunk in chunks[1:]:
            await message.channel.send(chunk)

    await bot.process_commands(message)


@bot.tree.command(
    name="ask",
    description="Chat with your Agentic Trading Lab agent (hosted model).",
)
@app_commands.describe(
    prompt="The message you want to send to your trading agent."
)
async def ask(
    interaction: discord.Interaction,
    prompt: str,
) -> None:
    # The deferred response is ephemeral, so only the invoking user sees it.
    await interaction.response.defer(
        thinking=True,
        ephemeral=True,
    )

    discord_user_id = str(interaction.user.id)

    chunks, error = await deliver_agent_chat(discord_user_id, prompt)
    if error:
        await interaction.edit_original_response(content=error)
        return

    for index, chunk in enumerate(chunks):
        if index == 0:
            await interaction.edit_original_response(content=chunk)
        else:
            await interaction.followup.send(
                chunk,
                ephemeral=True,
            )


@bot.tree.command(
    name="strategy",
    description="Turn your idea / chat into a trading strategy prompt you can backtest.",
)
@app_commands.describe(
    idea="Optional: describe your strategy. Omit to compile from your recent /ask chat.",
)
async def strategy(
    interaction: discord.Interaction,
    idea: Optional[str] = None,
) -> None:
    await interaction.response.defer(thinking=True, ephemeral=True)

    discord_user_id = str(interaction.user.id)
    selected = selected_agent_for(discord_user_id)
    agent_id = selected["agent_id"] if selected else DEFAULT_AGENT_ID

    try:
        prompt = await synthesize_strategy_prompt(
            user_id=discord_user_id,
            agent_id=agent_id,
            extra=idea,
        )
    except ValueError as exc:
        await interaction.edit_original_response(content=str(exc))
        return
    except Exception as exc:
        print("Discord /strategy synthesis failed:", repr(exc))
        await interaction.edit_original_response(
            content="Could not generate a strategy prompt. Check the hosted-model key and the bot terminal."
        )
        return

    try:
        record = await api_post(
            "/api/strategies",
            json={
                "prompt": prompt,
                "description": idea,
                "source": "discord",
                "owner": f"discord:{discord_user_id}",
            },
            # Per-user rate-limit key: without an id header the server's strategies
            # write limiter falls back to the peer IP, so every Discord user would
            # share this one bot process's single bucket. Key it per Discord user.
            headers={"X-Browser-Id": f"discord:{discord_user_id}"},
        )
    except Exception as exc:
        print("Discord /strategy store failed:", repr(exc))
        await interaction.edit_original_response(
            content=(
                "Generated a strategy but could not save it. Is the backend running "
                f"at `{api_base()}`? (set ATL_API_BASE if not)"
            )
        )
        return

    code = record.get("code")

    header = (
        f"**Strategy saved** · code `{code}`\n"
        "Click **Run backtest** below when you're ready.\n\n"
        "**Prompt:**\n"
    )
    body = f"```\n{prompt}\n```"
    view = StrategyRunBacktestView(discord_user_id=discord_user_id, code=str(code))

    chunks = split_discord_message(header + body)
    for index, chunk in enumerate(chunks):
        if index == 0:
            await interaction.edit_original_response(content=chunk, view=view)
        else:
            await interaction.followup.send(chunk, ephemeral=True)


@bot.tree.command(
    name="prompt",
    description="Show a saved strategy prompt by its share code.",
)
@app_commands.describe(code="The strategy share code (from /strategy).")
async def prompt_cmd(
    interaction: discord.Interaction,
    code: str,
) -> None:
    await interaction.response.defer(thinking=True, ephemeral=True)
    try:
        record = await api_get(f"/api/strategies/{code}")
    except Exception:
        await interaction.edit_original_response(content=f"No strategy found for code `{code}`.")
        return

    text = (
        f"**Strategy `{code}`**\n"
        f"{record.get('share_url', '')}\n\n"
        f"```\n{record.get('prompt', '')}\n```"
    )
    chunks = split_discord_message(text)
    for index, chunk in enumerate(chunks):
        if index == 0:
            await interaction.edit_original_response(content=chunk)
        else:
            await interaction.followup.send(chunk, ephemeral=True)


@bot.tree.command(
    name="backtest",
    description="Run a backtest from your own strategy prompt (real Alpaca data + hosted model).",
)
@app_commands.describe(
    prompt="Your strategy in plain language — used directly, no /strategy needed.",
    code="Optional saved strategy code (from /strategy); used only if no prompt is given.",
    start="Optional start date YYYY-MM-DD.",
    end="Optional end date YYYY-MM-DD.",
)
async def backtest_cmd(
    interaction: discord.Interaction,
    prompt: Optional[str] = None,
    code: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> None:
    await interaction.response.defer(thinking=True, ephemeral=True)

    discord_user_id = str(interaction.user.id)
    await execute_backtest(
        interaction,
        discord_user_id,
        prompt=prompt,
        code=code,
        start=start,
        end=end,
    )


@bot.tree.command(
    name="reset",
    description="Clear your temporary agent conversation.",
)
async def reset(
    interaction: discord.Interaction,
) -> None:
    discord_user_id = str(interaction.user.id)
    selected = selected_agent_for(discord_user_id)
    agent_id = selected["agent_id"] if selected else DEFAULT_AGENT_ID

    reset_agent_conversation(
        user_id=discord_user_id,
        agent_id=agent_id,
    )

    await interaction.response.send_message(
        "Your temporary agent conversation has been cleared.",
        ephemeral=True,
    )


@bot.tree.command(
    name="agent",
    description="List your linked website agents and choose which one to talk to.",
)
async def agent(
    interaction: discord.Interaction,
) -> None:
    await interaction.response.defer(thinking=True, ephemeral=True)

    discord_user_id = str(interaction.user.id)
    try:
        agents, err = await fetch_owned_agents(discord_user_id)
    except Exception as exc:
        print("Discord /agent fetch failed:", repr(exc))
        await interaction.edit_original_response(
            content=(
                "Could not load your agents. Is the backend running at "
                f"`{api_base()}`? (set ATL_API_BASE if not)"
            )
        )
        return

    if err == "discord_not_linked":
        await interaction.edit_original_response(
            content=(
                "Your Discord account is not linked to the website yet.\n"
                "On the lab site: **sign in → Open Discord** (authorize once). "
                "Then run `/agent` again to see *your* agents."
            )
        )
        return

    if err == "fetch_failed":
        await interaction.edit_original_response(
            content=(
                "Could not load your agents (auth/config error). "
                "Ask an admin to check `DISCORD_BOT_API_SECRET` on the API and bot."
            )
        )
        return

    # Backtest agent_id path requires builtin; keep externals visible but not selectable.
    selectable = [
        a for a in agents
        if (a.get("agent_type") or "external") == "builtin" and a.get("agent_id")
    ]

    # Drop stale in-memory selection if the agent is no longer owned.
    current = selected_agent_for(discord_user_id)
    owned_ids = {a["agent_id"] for a in agents if a.get("agent_id")}
    if current and current.get("agent_id") not in owned_ids:
        _selected_agents.pop(discord_user_id, None)
        current = None

    if not selectable:
        if agents:
            await interaction.edit_original_response(
                content=(
                    "Your linked account has agents, but none are **built-in** "
                    "(needed for Discord backtests).\n"
                    "On the website: **My Agents → Add Agent → Create a Built-in Agent**."
                )
            )
        else:
            await interaction.edit_original_response(
                content=(
                    "No agents on your linked website account yet.\n"
                    "Create one on the site: **My Agents → Add Agent → "
                    "Create a Built-in Agent**, then run `/agent` again."
                )
            )
        return

    lines = ["**Your agents** (linked website account)"]
    for a in selectable[:25]:
        marker = "✅ " if current and current["agent_id"] == a["agent_id"] else "• "
        lines.append(
            f"{marker}**{a.get('name')}** — `{a.get('model_name') or 'local-model'}` "
            f"· {a.get('run_count', 0)} backtest(s)"
        )
    if current:
        lines.append(f"\nCurrently selected: **{current['name']}**")
    lines.append("\nPick one below, then message the bot directly (or use `/ask`).")

    await interaction.edit_original_response(
        content="\n".join(lines),
        view=AgentSelectView(selectable),
    )


def main() -> None:
    bot.run(require_env("DISCORD_BOT_TOKEN"))


if __name__ == "__main__":
    main()
