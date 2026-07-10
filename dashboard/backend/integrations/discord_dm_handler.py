"""DM conversation handler for the ATL Discord bot."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, List, Optional

import discord

from dashboard.backend.integrations import discord_api_client as api
from dashboard.backend.integrations.discord_intents import (
  DEFAULT_BACKTEST_END,
  DEFAULT_BACKTEST_START,
  INTENT_CHECK_STATUS,
  INTENT_CONNECT,
  INTENT_HELP,
  INTENT_RUN_BACKTEST,
  INTENT_SELECT_AGENT,
  INTENT_SHOW_AGENTS,
  INTENT_UNKNOWN,
  format_backtest_confirmation,
  help_message,
  route_intent,
)

NOT_LINKED_MSG = (
  "Your Discord is not linked to an ATL account yet.\n"
  "Say **`connect`** and I'll send you a link to log in on the website."
)

ATL_DM_WELCOME = (
  "Hi, this is your private **ATL trading agent** chat. You can say things like:\n"
  "• `connect` — link your ATL website account (start here if you're new)\n"
  "• `show my agents`\n"
  "• `use my momentum agent`\n"
  "• `run backtest on AAPL MSFT last month`\n"
  "• `show my latest result`"
)


def format_connect_instructions(result: Dict[str, Any]) -> str:
  if result.get("linked"):
    return "Your Discord is already linked. Say `show my agents` to get started."
  url = result.get("connect_url", "")
  return (
    "**Link your ATL account**\n"
    f"1. Open: {url}\n"
    "2. Log in on the website\n"
    "3. Confirm linking\n\n"
    "This code expires in 30 minutes. Your website password stays on the site — "
    "nothing sensitive is sent to Discord."
  )


async def deliver_connect_instructions(
  *,
  discord_user_id: str,
  discord_username: Optional[str] = None,
  guild_id: Optional[str] = None,
) -> tuple[Optional[str], Optional[str]]:
  """Return ``(message, error)`` — one of them is set."""
  try:
    result = await asyncio.to_thread(
      api.create_connect_token,
      discord_user_id=discord_user_id,
      discord_username=discord_username,
      guild_id=guild_id,
    )
  except Exception as exc:
    print("Discord connect token failed:", repr(exc))
    return None, "Could not reach the ATL backend. Try again in a moment."
  return format_connect_instructions(result), None


def _match_agent(agents: List[Dict[str, Any]], query: str) -> Optional[Dict[str, Any]]:
  q = query.strip().lower()
  if not q:
    return None
  for agent in agents:
    name = (agent.get("name") or "").lower()
    if name == q or q in name or name in q:
      return agent
  return None


class AtlAgentSelect(discord.ui.Select):
  def __init__(self, agents: List[Dict[str, Any]], discord_user_id: str):
    options: List[discord.SelectOption] = []
    for agent in agents[:25]:
      model = agent.get("model_name") or "local-model"
      options.append(
        discord.SelectOption(
          label=(agent.get("name") or "agent")[:100],
          value=agent["agent_id"],
          description=f"{model} · {agent.get('run_count', 0)} run(s)"[:100],
        )
      )
    super().__init__(
      placeholder="Choose an agent…",
      min_values=1,
      max_values=1,
      options=options,
    )
    self._agents = {a["agent_id"]: a for a in agents}
    self.discord_user_id = discord_user_id

  async def callback(self, interaction: discord.Interaction) -> None:
    if str(interaction.user.id) != self.discord_user_id:
      await interaction.response.send_message("This menu is for another user.", ephemeral=True)
      return
    agent = self._agents.get(self.values[0])
    if not agent:
      await interaction.response.edit_message(content="Agent not found.", view=None)
      return
    await asyncio.to_thread(
      api.patch_session,
      self.discord_user_id,
      selected_agent_id=agent["agent_id"],
    )
    await interaction.response.edit_message(
      content=f"Selected **{agent.get('name')}**. Say `run backtest on AAPL last month` when ready.",
      view=None,
    )


class AtlAgentSelectView(discord.ui.View):
  def __init__(self, agents: List[Dict[str, Any]], discord_user_id: str, *, timeout: float = 120):
    super().__init__(timeout=timeout)
    self.add_item(AtlAgentSelect(agents, discord_user_id))


class AtlBacktestConfirmView(discord.ui.View):
  def __init__(
    self,
    *,
    discord_user_id: str,
    agent_id: str,
    agent_name: str,
    config: Dict[str, Any],
    timeout: float = 180,
  ):
    super().__init__(timeout=timeout)
    self.discord_user_id = discord_user_id
    self.agent_id = agent_id
    self.agent_name = agent_name
    self.config = config

  async def interaction_check(self, interaction: discord.Interaction) -> bool:
    if str(interaction.user.id) != self.discord_user_id:
      await interaction.response.send_message("This confirmation is for another user.", ephemeral=True)
      return False
    return True

  @discord.ui.button(label="Run Backtest", style=discord.ButtonStyle.green)
  async def run_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
    await interaction.response.defer()
    symbols = self.config.get("symbols") or []
    start = self.config.get("start_date") or DEFAULT_BACKTEST_START
    end = self.config.get("end_date") or DEFAULT_BACKTEST_END
    try:
      result = await asyncio.to_thread(
        api.create_backtest,
        discord_user_id=self.discord_user_id,
        agent_id=self.agent_id,
        symbols=symbols,
        start_date=start,
        end_date=end,
      )
    except Exception as exc:
      print("Discord backtest create failed:", repr(exc))
      await interaction.edit_original_response(
        content="Could not queue the backtest. Is the ATL backend running?",
        view=None,
      )
      return
  # Also try real /backtest/run via existing flow
    await _try_run_real_backtest(
      discord_user_id=self.discord_user_id,
      agent_id=self.agent_id,
      start=start,
      end=end,
    )
    run_id = result.get("run_id", "?")
    url = result.get("dashboard_url", "")
    await interaction.edit_original_response(
      content=(
        f"**Backtest queued.** Run ID: `{run_id}`\n"
        f"Agent: **{self.agent_name}**\n"
        f"Say `status` later to check progress.\n"
        f"View: {url}"
      ),
      view=None,
    )

  @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
  async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
    await asyncio.to_thread(api.patch_session, self.discord_user_id, clear_pending=True)
    await interaction.response.edit_message(content="Backtest cancelled.", view=None)


async def _try_run_real_backtest(
  *,
  discord_user_id: str,
  agent_id: str,
  start: str,
  end: str,
) -> None:
  """Best-effort call to the existing /backtest/run endpoint when an agent session exists."""
  try:
    agents = await asyncio.to_thread(api.list_agents, discord_user_id)
    agent = next((a for a in agents if a["agent_id"] == agent_id), None)
    if not agent or not agent.get("session_id"):
      return
    await asyncio.to_thread(
      api.run_legacy_backtest,
      session_id=agent["session_id"],
      agent_id=agent_id,
      start_date=start,
      end_date=end,
    )
  except Exception as exc:
    print("Discord optional /backtest/run failed:", repr(exc))


async def handle_dm_message(
  message: discord.Message,
  *,
  reply: Callable[..., Awaitable[Any]],
) -> bool:
  """Process a DM through the intent router. Returns True if handled."""
  if not isinstance(message.channel, discord.DMChannel):
    return False
  if message.author.bot:
    return True

  discord_user_id = str(message.author.id)
  text = (message.content or "").strip()
  if not text:
    return True

  routed = route_intent(text)

  if routed.intent == INTENT_HELP:
    await reply(help_message())
    return True

  if routed.intent == INTENT_CONNECT:
    msg, err = await deliver_connect_instructions(
      discord_user_id=discord_user_id,
      discord_username=str(message.author),
    )
    await reply(err or msg or "Something went wrong.")
    return True

  try:
    link = await asyncio.to_thread(api.get_account_link, discord_user_id)
  except Exception as exc:
    print("Discord link check failed:", repr(exc))
    await reply("Cannot reach the ATL backend. Try again later.")
    return True

  if not link.get("linked"):
    await reply(NOT_LINKED_MSG)
    return True

  if routed.intent == INTENT_SHOW_AGENTS:
    try:
      agents = await asyncio.to_thread(api.list_agents, discord_user_id)
    except Exception:
      await reply("Could not load your agents. Try again later.")
      return True
    if not agents:
      await reply("You have no agents yet. Create one at the ATL website under **My Agents**.")
      return True
    lines = ["**Your agents:**"]
    session_data = await asyncio.to_thread(api.get_session, discord_user_id)
    selected_id = (session_data.get("session") or {}).get("selected_agent_id")
    for a in agents[:25]:
      mark = "✅ " if a["agent_id"] == selected_id else "• "
      lines.append(f"{mark}**{a.get('name')}** — `{a.get('model_name', 'local-model')}`")
    lines.append("\nPick one below or say `use <name> agent`.")
    view = AtlAgentSelectView(agents, discord_user_id)
    await reply("\n".join(lines), view=view)
    return True

  if routed.intent == INTENT_SELECT_AGENT:
    try:
      agents = await asyncio.to_thread(api.list_agents, discord_user_id)
    except Exception:
      await reply("Could not load your agents.")
      return True
    agent = _match_agent(agents, routed.agent_query or "")
    if not agent:
      await reply(
        f"No agent matching **{routed.agent_query}**. Say `show my agents` to pick from the list."
      )
      return True
    await asyncio.to_thread(api.patch_session, discord_user_id, selected_agent_id=agent["agent_id"])
    await reply(f"Using **{agent.get('name')}**. Ready for backtests.")
    return True

  if routed.intent == INTENT_RUN_BACKTEST:
    session_data = await asyncio.to_thread(api.get_session, discord_user_id)
    session = session_data.get("session") or {}
    agent_id = session.get("selected_agent_id")
    if not agent_id:
      await reply("Select an agent first. Say `show my agents` or `use <name> agent`.")
      return True
    try:
      agents = await asyncio.to_thread(api.list_agents, discord_user_id)
    except Exception:
      await reply("Could not verify your agent.")
      return True
    agent = next((a for a in agents if a["agent_id"] == agent_id), None)
    if not agent:
      await reply("Selected agent not found. Pick an agent again.")
      return True
    cfg = routed.backtest
    start = cfg.get("start_date") or DEFAULT_BACKTEST_START
    end = cfg.get("end_date") or DEFAULT_BACKTEST_END
    symbols = cfg.get("symbols") or []
    if not cfg.get("start_date") or not cfg.get("end_date"):
      await reply(
        "I need a date range. Example: `run backtest on AAPL MSFT from 2026-06-01 to 2026-06-30` "
        "or `last month`."
      )
      return True
    pending = {
      "agent_id": agent_id,
      "agent_name": agent.get("name"),
      "symbols": symbols,
      "start_date": start,
      "end_date": end,
      "initial_capital": cfg.get("initial_capital", 100_000),
    }
    await asyncio.to_thread(api.patch_session, discord_user_id, pending_backtest=pending)
    body = format_backtest_confirmation(
      agent_name=agent.get("name") or "Agent",
      symbols=symbols,
      start_date=start,
      end_date=end,
      initial_capital=int(pending["initial_capital"]),
    )
    view = AtlBacktestConfirmView(
      discord_user_id=discord_user_id,
      agent_id=agent_id,
      agent_name=agent.get("name") or "Agent",
      config=pending,
    )
    await reply(body, view=view)
    return True

  if routed.intent == INTENT_CHECK_STATUS:
    try:
      status = await asyncio.to_thread(api.latest_run, discord_user_id)
    except Exception:
      await reply("Could not fetch run status.")
      return True
    if status.get("status") == "none":
      await reply(status.get("message", "No runs yet."))
      return True
    metrics = status.get("metrics") or {}
    if metrics:
      ret = metrics.get("total_return")
      ret_s = f"{float(ret) * 100:.2f}%" if ret is not None else "—"
      await reply(
        f"**Latest backtest** (`{metrics.get('run_id', status.get('run_id'))}`)\n"
        f"Return: **{ret_s}** · Window: {metrics.get('start_date')} → {metrics.get('end_date')}\n"
        f"View: {status.get('dashboard_url', '')}"
      )
    else:
      await reply(
        f"Run `{status.get('run_id')}` is **{status.get('status', 'queued')}**. "
        "Check again in a few minutes."
      )
    return True

  if routed.intent == INTENT_UNKNOWN:
    await reply(
      "I didn't understand that.\n\n" + help_message()
    )
    return True

  return False
