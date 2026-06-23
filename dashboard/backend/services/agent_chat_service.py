"""Compatibility shim for the agent-chat service.

The implementation moved (Phase 3D3A) to
``dashboard.backend.domain.chat.service``. This module re-exports the public API
and module-level singletons so legacy imports keep working with identical
behavior and object identity. The canonical module is import-safe (Phase 3D3B):
credentials and the Anthropic client are resolved lazily at execution time, not
at import.
"""

from dashboard.backend.domain.chat.service import (  # noqa: F401
    SYSTEM_PROMPT,
    chat_with_agent,
    conversation_history,
    extract_text,
    get_claude_client,
    require_env,
    reset_agent_conversation,
)

__all__ = [
    "SYSTEM_PROMPT",
    "chat_with_agent",
    "conversation_history",
    "extract_text",
    "get_claude_client",
    "require_env",
    "reset_agent_conversation",
]
