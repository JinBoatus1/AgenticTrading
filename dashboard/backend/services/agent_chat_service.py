"""Compatibility shim for the agent-chat service.

The implementation moved (Phase 3D3A) to
``dashboard.backend.domain.chat.service``. This module re-exports the public API
and module-level singletons so legacy imports keep working with identical
behavior and object identity. Import-time credential/env requirements are
preserved transitively through the canonical module.
"""

from dashboard.backend.domain.chat.service import (  # noqa: F401
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    SYSTEM_PROMPT,
    chat_with_agent,
    claude_client,
    conversation_history,
    extract_text,
    require_env,
    reset_agent_conversation,
)

__all__ = [
    "SYSTEM_PROMPT",
    "chat_with_agent",
    "conversation_history",
    "extract_text",
    "require_env",
    "reset_agent_conversation",
]
