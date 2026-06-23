from __future__ import annotations

import os
from collections import defaultdict
from typing import Any

from anthropic import AsyncAnthropic
from dotenv import load_dotenv


load_dotenv()


def require_env(name: str) -> str:
    value = os.getenv(name)

    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")

    return value


# Lazily-constructed Anthropic client.
#
# Importing this module must not require credentials or build a network client;
# the client is created on first use via ``get_claude_client`` so that import
# stays side-effect free and test/runtime configuration is resolved on demand.
_claude_client: AsyncAnthropic | None = None


def get_claude_client() -> AsyncAnthropic:
    """Return the shared Anthropic client, constructing it on first use."""
    global _claude_client

    if _claude_client is None:
        _claude_client = AsyncAnthropic(api_key=require_env("ANTHROPIC_API_KEY"))

    return _claude_client


# Temporary MVP memory.
#
# Key:
#   (platform_user_id, agent_id)
#
# Value:
#   Claude-compatible conversation messages
#
# This will eventually be replaced with persistent database storage.
conversation_history: dict[
    tuple[str, str],
    list[dict[str, Any]],
] = defaultdict(list)


SYSTEM_PROMPT = """
You are the conversational assistant for Agentic Trading Lab.

Agentic Trading Lab helps users experiment with LLM-based trading agents,
including backtesting, paper trading, strategy configuration, performance
evaluation, and decision analysis.

This Discord integration is currently an early chat prototype.

Do not claim that you:
- executed a trade,
- changed a saved strategy,
- accessed a portfolio,
- ran a backtest,
- retrieved live market data,

unless the application provides an actual tool result confirming that action.

Provide educational and research-oriented assistance. Clearly distinguish
general information from personalized financial advice.
""".strip()


def extract_text(response: Any) -> str:
    parts: list[str] = []

    for block in response.content:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)

    return "\n".join(parts).strip()


async def chat_with_agent(
    *,
    user_id: str,
    agent_id: str,
    message: str,
) -> str:
    """
    Send a message to an Agentic Trading Lab agent.

    This function is the main integration boundary. The Discord bot should
    not call Anthropic directly.

    Future implementation:
    - authenticate the platform user,
    - verify agent ownership,
    - retrieve durable memory,
    - load the selected agent configuration,
    - expose approved trading tools,
    - save messages and tool results.
    """
    cleaned_message = message.strip()

    if not cleaned_message:
        raise ValueError("Message cannot be empty.")

    key = (user_id, agent_id)
    history = conversation_history[key]

    history.append(
        {
            "role": "user",
            "content": cleaned_message,
        }
    )

    # Keep only the latest six user-assistant exchanges for the MVP.
    if len(history) > 12:
        del history[:-12]

    try:
        model = require_env("ANTHROPIC_MODEL")
        client = get_claude_client()

        response = await client.messages.create(
            model=model,
            max_tokens=1200,
            system=SYSTEM_PROMPT,
            messages=history,
        )
    except Exception:
        # Avoid retaining a user message that never received an answer.
        if history and history[-1]["role"] == "user":
            history.pop()

        raise

    answer = extract_text(response)

    if not answer:
        answer = "Claude returned an empty response."

    history.append(
        {
            "role": "assistant",
            "content": answer,
        }
    )

    if len(history) > 12:
        del history[:-12]

    return answer


def reset_agent_conversation(
    *,
    user_id: str,
    agent_id: str,
) -> None:
    key = (user_id, agent_id)
    conversation_history.pop(key, None)
