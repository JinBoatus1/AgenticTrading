"""LLM backtest harness: external model-interaction infrastructure.

Extracted (Phase 2C2) from ``PortfolioManager.make_trading_decision_with_llm`` in
``dashboard/scripts/backtest_hourly_agent.py``. This module owns the *external
LLM infrastructure* concerns only:

* the optional Anthropic SDK import (``Anthropic`` / ``HAS_ANTHROPIC``);
* the default model name (``LLM_MODEL_NAME``);
* the system prompt and request parameters;
* Anthropic client invocation / prompt submission;
* response-text extraction;
* token-usage extraction;
* response parsing with the existing JSON-repair fallbacks.

Business rules (market-snapshot construction, action conversion, position
sizing, rule-based fallback) and portfolio/manager-state mutation deliberately
remain in the legacy ``PortfolioManager`` wrapper. Behavior here is byte-for-byte
identical to the original inline logic.

This module reuses the already-extracted ``fix_json_formatting`` from
``dashboard.backend.infrastructure.llm.decision_parsing`` (no duplication) and is
domain/infrastructure-only: it must NOT import FastAPI, API routers, the database
singleton, Alpaca clients, dashboard scripts, ``PortfolioManager``, or
``HourlyBacktester``. Importing it is safe without an Anthropic API key (the SDK
import is optional and there is no import-time network or credential access).
"""

import json
from typing import Dict, Optional

from dashboard.backend.infrastructure.llm.decision_parsing import fix_json_formatting

# Optional: LLM integration. Mirrors the original optional-dependency behavior
# (no API key required at import time; only the SDK presence is detected).
try:
    from anthropic import Anthropic
    HAS_ANTHROPIC = True
except ImportError:
    # Bind ``Anthropic`` to None (instead of leaving it undefined) so the legacy
    # script can unconditionally re-export it; consumers always guard on
    # ``HAS_ANTHROPIC`` before using the client.
    Anthropic = None
    HAS_ANTHROPIC = False
    print("⚠️  Anthropic SDK not installed. Fallback to rule-based trading.")
    print("   To enable LLM: pip install anthropic")

# Default model name (model selection). Re-exported by the legacy script.
LLM_MODEL_NAME = "claude-haiku-4-5-20251001"  # Change this to switch models

# System prompt sent on every request. Preserved exactly from the original
# inline string (do not "improve" it).
SYSTEM_PROMPT = """You are an expert quantitative trading advisor analyzing DJIA stocks.

You have deep knowledge of:
- Technical analysis (RSI, MACD, Bollinger Bands, Moving Averages)
- Indicator interpretation and confluence
- Risk management and position sizing
- Trading psychology and market microstructure

IMPORTANT INSTRUCTIONS:
1. Analyze EACH stock signal provided (don't skip any)
2. For each stock, decide: BUY, SELL, or HOLD
3. Always include a confidence score (0.0-1.0)
4. Return a JSON object with an "actions" array containing one entry per stock
5. Even if you decide HOLD, include it in the actions array
6. Respond with ONLY valid JSON - no explanations outside JSON

Make precise, actionable trading decisions based on the technical indicators provided."""


def request_trading_decision(client, *, prompt: str, model: Optional[str] = None, max_tokens: int = 2000):
    """Submit the prompt to the Anthropic client and return the raw response.

    Mirrors the original ``llm_client.messages.create(...)`` call exactly: same
    model resolution (``model or LLM_MODEL_NAME``), ``max_tokens=2000``, system
    prompt, and single user message. Exceptions are intentionally NOT caught here
    so the legacy wrapper's outer handler can fall back to rule-based logic,
    exactly as before.
    """
    return client.messages.create(
        model=model or LLM_MODEL_NAME,
        max_tokens=max_tokens,  # Reduced from 3000 (saves tokens)
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )


def extract_response_text(response) -> str:
    """Extract the response text exactly as the original (``content[0].text``)."""
    return response.content[0].text


def extract_token_usage(response):
    """Return ``(input_tokens, output_tokens)`` deltas from a provider response.

    Mirrors the original usage reads: ``getattr(response, "usage", None)`` then
    ``int(getattr(usage, "input_tokens", 0) or 0)`` etc., returning ``(0, 0)``
    when no usage object is present. The caller is responsible for applying these
    to manager state and incrementing the call counter (kept in the wrapper).
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        return 0, 0
    return (
        int(getattr(usage, "input_tokens", 0) or 0),
        int(getattr(usage, "output_tokens", 0) or 0),
    )


def parse_llm_response(llm_response: str) -> Optional[Dict]:
    """Parse the LLM response into a decision dict, or ``None`` on failure.

    Replicates the original STEP-3 parsing exactly: strip markdown fences, slice
    from the first ``{`` to the last ``}``, ``json.loads`` with two escalating
    ``fix_json_formatting`` / bracket-balancing repair attempts, and the same
    printed diagnostics. Returns the parsed ``decision`` dict on success.

    Returns ``None`` in every case where the original method returned
    ``{"actions": []}`` (no JSON found, unrecoverable parse error, or any other
    exception in the parse block), so the caller can return ``{"actions": []}``
    and preserve behavior.
    """
    print(f"\n📫 Parsing LLM response...")
    print(f"   Raw response (first 300 chars): {llm_response[:300]}")

    try:
        # Extract JSON from response
        # First, strip markdown code fences if present
        response_cleaned = llm_response
        if '```json' in response_cleaned:
            response_cleaned = response_cleaned.replace('```json', '').replace('```', '')
        elif '```' in response_cleaned:
            response_cleaned = response_cleaned.replace('```', '')

        start = response_cleaned.find('{')
        end = response_cleaned.rfind('}') + 1
        if start < 0 or end <= 0:
            print(f"   ❌ No JSON found in response")
            print(f"   Full response: {response_cleaned[:500]}")
            return None

        json_str = response_cleaned[start:end]

        # Try to parse
        try:
            decision = json.loads(json_str)
            print(f"   ✅ JSON parsed successfully")
        except json.JSONDecodeError as e:
            # Try to fix common formatting issues
            print(f"   ⚠️  Initial parse failed: {e}")
            print(f"   Attempting to fix JSON formatting...")

            json_str_fixed = fix_json_formatting(json_str)
            try:
                decision = json.loads(json_str_fixed)
                print(f"   ✅ JSON fixed and parsed successfully!")
            except json.JSONDecodeError as e2:
                print(f"   ❌ Still failed after fix: {e2}")
                print(f"   Error at line {e2.lineno}, column {e2.colno}")

                # Show detailed context around error
                lines = json_str_fixed.split('\n')
                if e2.lineno <= len(lines):
                    start = max(0, e2.lineno - 3)
                    end = min(len(lines), e2.lineno + 2)
                    print(f"\n   Context around error (lines {start+1}-{end}):")
                    for i in range(start, end):
                        marker = ">> " if i == e2.lineno - 1 else "   "
                        print(f"   {marker}{i+1:3d}: {lines[i][:70]}")

                # Try one more aggressive fix
                print(f"\n   Attempting second fix attempt (validate structure)...")
                try:
                    # Count opening vs closing brackets
                    open_count = json_str_fixed.count('{')
                    close_count = json_str_fixed.count('}')
                    if open_count != close_count:
                        print(f"   Bracket mismatch: {open_count} open, {close_count} close")
                        # Remove extra closing brackets from the end
                        while json_str_fixed.count('}') > json_str_fixed.count('{'):
                            json_str_fixed = json_str_fixed.rsplit('}', 1)[0] + '}'
                        print(f"   Removed extra closing brackets")

                    decision = json.loads(json_str_fixed)
                    print(f"   ✅ JSON fixed after structure cleanup!")
                except json.JSONDecodeError as e3:
                    print(f"   ❌ Cannot fix: {e3}")
                    return None

        print(f"   Actions from LLM: {len(decision.get('actions', []))}")
        return decision

    except (json.JSONDecodeError, ValueError, Exception) as e:
        print(f"   ❌ Failed to parse JSON: {e}")
        print(f"   LLM response: {llm_response[:500]}...")
        return None
