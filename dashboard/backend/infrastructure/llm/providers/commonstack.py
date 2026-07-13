"""CommonStack gateway integration.

CommonStack exposes OpenAI / Google / xAI / DeepSeek / Qwen / Anthropic models
behind one key on an Anthropic-compatible ``/v1/messages`` surface. Responses
keep Anthropic shape (``content[0].text`` + ``usage.{input,output}_tokens``),
so the shared backtest harness needs only a different ``base_url`` and a
``provider/model`` slug.
"""

from __future__ import annotations

import os
from typing import Any, Optional

INTEGRATION_ID = "commonstack"
DEFAULT_MODEL = "anthropic/claude-haiku-4-5"
DEFAULT_BASE_URL = "https://api.commonstack.ai"


def base_url() -> str:
    return os.getenv("COMMONSTACK_BASE_URL", DEFAULT_BASE_URL)


def default_model_name() -> str:
    return DEFAULT_MODEL


def make_client(anthropic_cls: Any) -> Optional[Any]:
    """Build an Anthropic-compatible client for CommonStack, or ``None``."""
    key = os.getenv("COMMONSTACK_API_KEY")
    if not key:
        return None
    try:
        return anthropic_cls(api_key=key, base_url=base_url())
    except Exception as exc:  # pragma: no cover - defensive
        print(f"⚠️  Failed to init CommonStack client: {exc}")
        return None
