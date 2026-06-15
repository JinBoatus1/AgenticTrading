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


ANTHROPIC_API_KEY = require_env("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = require_env("ANTHROPIC_MODEL")

claude_client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)


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
        response = await claude_client.messages.create(
            model=ANTHROPIC_MODEL,
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