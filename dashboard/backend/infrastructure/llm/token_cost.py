"""Token usage and dollar-cost estimation for agent runs.

External agents run their own LLM client side, so the backend never sees the
real token counts. Instead we estimate input tokens from the market context the
backend serves each hour and output tokens from the decisions the agent submits.
For server-side LLM calls (the internal hourly backtester) we can record the
real usage reported by the provider, so those numbers are exact.

The estimator is deliberately dependency-free (no tiktoken / network calls) so
it can run anywhere. It uses a characters-per-token heuristic that is a good
approximation for the JSON-heavy payloads this app exchanges.
"""

from __future__ import annotations

import json
import math
from typing import Any, Tuple

# JSON / structured text packs slightly more tokens per character than prose.
# ~3.8 chars/token tracks Claude + GPT tokenizers well for this payload shape.
CHARS_PER_TOKEN = 3.8

# Approximate USD pricing per 1,000,000 tokens (input, output).
# Matched by substring against the run's model name (longest/most specific first).
# "Local" / rule-based models incur no API cost.
_PRICING_TABLE: list[Tuple[str, float, float]] = [
    # CommonStack-verified slugs (provider/model), rates from GET /v1/models on
    # 2026-06-24. Listed first so the specific slug wins over generic needles.
    ("openai/gpt-5.5", 5.0, 30.0),
    ("google/gemini-3.1-pro", 2.0, 12.0),
    ("anthropic/claude-sonnet-4-6", 3.0, 15.0),
    ("deepseek/deepseek-v4-pro", 0.435, 0.87),
    ("qwen/qwen3.7-plus", 0.40, 1.60),
    ("x-ai/grok-4.20-reasoning", 1.25, 2.50),  # listed but unavailable on our account (no channel)
    ("claude-opus-4", 15.0, 75.0),
    ("claude-sonnet-4", 3.0, 15.0),
    ("claude-haiku-4", 1.0, 5.0),
    ("claude-3-7-sonnet", 3.0, 15.0),
    ("claude-3-5-sonnet", 3.0, 15.0),
    ("claude-3-5-haiku", 0.80, 4.0),
    ("claude-3-opus", 15.0, 75.0),
    ("claude-3-haiku", 0.25, 1.25),
    ("opus", 15.0, 75.0),
    ("sonnet", 3.0, 15.0),
    ("haiku", 1.0, 5.0),
    ("gpt-4o-mini", 0.15, 0.60),
    ("gpt-4o", 2.50, 10.0),
    ("gpt-4.1-mini", 0.40, 1.60),
    ("gpt-4.1", 2.0, 8.0),
    ("o3-mini", 1.10, 4.40),
    ("o3", 2.0, 8.0),
    ("gpt-4-turbo", 10.0, 30.0),
    ("gpt-4", 30.0, 60.0),
    ("gpt-3.5", 0.50, 1.50),
]

# Model names that represent no paid LLM call (cost = 0).
_FREE_MODEL_MARKERS = ("rule-based", "local-model", "local", "demo", "baseline", "none")

# Fallback pricing when a real-looking model name is not in the table.
_DEFAULT_PRICING: Tuple[float, float] = (1.0, 5.0)


def is_free_model(model: str | None) -> bool:
    """True when ``model`` names no real paid LLM: a sentinel / rule-based /
    local marker (e.g. ``'local-model'``, ``'rule-based'``) or nothing at all.

    Callers use this to treat such values as "no explicit model" rather than a
    real model id — e.g. the Discord bot must not forward the default
    ``'local-model'`` sentinel to the hosted-model API as if it were a model."""
    name = (model or "").strip().lower()
    if not name:
        return True
    return any(marker in name for marker in _FREE_MODEL_MARKERS)


def is_known_model(model: str | None) -> bool:
    """True when ``model`` is a recognized model id an endpoint may run.

    A model is "known" if it is a free/local marker (or empty → "use default"),
    or its name matches a family in ``_PRICING_TABLE`` (same substring rule
    ``price_for_model`` uses). Public endpoints allowlist against this so an
    anonymous caller cannot force an arbitrary/unpriced model and spend operator
    credits. Kept here so the allowlist stays a single source of truth with the
    pricing table.
    """
    if is_free_model(model):
        return True
    name = (model or "").strip().lower()
    return any(needle in name for needle, _in, _out in _PRICING_TABLE)


def estimate_tokens(value: Any) -> int:
    """Estimate the number of tokens in a string or JSON-serializable object."""
    if value is None:
        return 0
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, separators=(",", ":"), default=str)
        except (TypeError, ValueError):
            text = str(value)
    if not text:
        return 0
    return max(1, math.ceil(len(text) / CHARS_PER_TOKEN))


def price_for_model(model: str | None) -> Tuple[float, float]:
    """Return (input_usd_per_mtok, output_usd_per_mtok) for a model name."""
    name = (model or "").strip().lower()
    if not name:
        return _DEFAULT_PRICING
    if any(marker in name for marker in _FREE_MODEL_MARKERS):
        return (0.0, 0.0)
    for needle, in_price, out_price in _PRICING_TABLE:
        if needle in name:
            return (in_price, out_price)
    return _DEFAULT_PRICING


def estimate_cost_usd(model: str | None, input_tokens: int, output_tokens: int) -> float:
    """Estimate the USD cost of a run given token counts and a model name."""
    in_price, out_price = price_for_model(model)
    cost = (input_tokens / 1_000_000) * in_price + (output_tokens / 1_000_000) * out_price
    return round(cost, 6)


def summarize(
    model: str | None,
    input_tokens: int,
    output_tokens: int,
    llm_calls: int = 0,
) -> dict[str, Any]:
    """Build a serializable token/cost summary for storage or API responses."""
    input_tokens = int(input_tokens or 0)
    output_tokens = int(output_tokens or 0)
    return {
        "model": model,
        "llm_calls": int(llm_calls or 0),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "est_cost_usd": estimate_cost_usd(model, input_tokens, output_tokens),
    }
