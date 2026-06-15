from __future__ import annotations

import os

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from backend.services.agent_chat_service import (
    chat_with_agent,
    reset_agent_conversation,
)


load_dotenv()


def require_env(name: str) -> str:
    value = os.getenv(name)

    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")

    return value


DISCORD_BOT_TOKEN = require_env("DISCORD_BOT_TOKEN")
DISCORD_GUILD_ID = int(require_env("DISCORD_GUILD_ID"))

# The MVP gives every user one placeholder agent.
# Later, replace this with the user's selected agent from the database.
DEFAULT_AGENT_ID = "default"


def split_discord_message(
    text: str,
    limit: int = 1800,
) -> list[str]:
    """
    Split long Claude responses into Discord-safe chunks.
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


class AgenticTradingDiscordBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()

        super().__init__(
            command_prefix="!",
            intents=intents,
        )

    async def setup_hook(self) -> None:
        """
        Sync commands to one development server.

        Guild-level synchronization makes development commands appear
        quickly. Production can later use global commands.
        """
        guild = discord.Object(id=DISCORD_GUILD_ID)

        self.tree.copy_global_to(guild=guild)
        synced_commands = await self.tree.sync(guild=guild)

        print(
            f"Synced {len(synced_commands)} Discord command(s) "
            f"to guild {DISCORD_GUILD_ID}."
        )


bot = AgenticTradingDiscordBot()


@bot.event
async def on_ready() -> None:
    if bot.user is not None:
        print(f"Discord bot connected as {bot.user}.")


@bot.tree.command(
    name="ask",
    description="Talk privately to your Agentic Trading Lab agent.",
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

    try:
        answer = await chat_with_agent(
            user_id=discord_user_id,
            agent_id=DEFAULT_AGENT_ID,
            message=prompt,
        )

        chunks = split_discord_message(answer)

        for index, chunk in enumerate(chunks):
            if index == 0:
                await interaction.edit_original_response(content=chunk)
            else:
                await interaction.followup.send(
                    chunk,
                    ephemeral=True,
                )

    except Exception as exc:
        print(
            "Discord /ask request failed:",
            repr(exc),
        )

        await interaction.edit_original_response(
            content=(
                "The Claude request failed. Check the bot terminal and "
                "verify the Discord token, Anthropic key, model ID, and "
                "Anthropic API balance."
            )
        )


@bot.tree.command(
    name="reset",
    description="Clear your temporary agent conversation.",
)
async def reset(
    interaction: discord.Interaction,
) -> None:
    discord_user_id = str(interaction.user.id)

    reset_agent_conversation(
        user_id=discord_user_id,
        agent_id=DEFAULT_AGENT_ID,
    )

    await interaction.response.send_message(
        "Your temporary agent conversation has been cleared.",
        ephemeral=True,
    )


@bot.tree.command(
    name="agent",
    description="Show the agent currently connected to Discord.",
)
async def agent(
    interaction: discord.Interaction,
) -> None:
    await interaction.response.send_message(
        (
            f"Current agent: `{DEFAULT_AGENT_ID}`\n\n"
            "This is the MVP placeholder agent. Later, this command will "
            "show and select agents owned by your Agentic Trading Lab account."
        ),
        ephemeral=True,
    )


if __name__ == "__main__":
    bot.run(DISCORD_BOT_TOKEN)