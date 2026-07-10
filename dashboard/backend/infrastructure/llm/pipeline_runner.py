"""Sequential sub-agent pipeline executor for hourly backtest decisions.

Each pipeline step is one LLM call. Step 1 receives the market snapshot;
later steps receive upstream JSON outputs. The final step should emit either
``actions`` (standard trading contract) or ``orders`` / ``risk_actions`` which
are normalized into ``actions`` for the existing portfolio executor.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from dashboard.backend.infrastructure.llm.backtest_harness import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    LLM_MODEL_NAME,
    extract_response_text,
    extract_token_usage,
    parse_llm_response,
)

PIPELINE_SYSTEM_PROMPT = """You are a sub-agent in a multi-step trading pipeline.
Follow your task instructions precisely.
Return ONLY valid JSON matching the required output format.
No markdown, no code fences, no explanatory text outside the JSON."""


def _build_step_prompt(
    *,
    step_index: int,
    step: Dict[str, Any],
    market_snapshot: Dict[str, Any],
    prior_outputs: List[Dict[str, Any]],
    is_last: bool,
) -> str:
    label = (step.get("label") or f"Step {step_index + 1}").strip()
    task = (step.get("prompt") or "").strip()
    output_format = (step.get("outputFormat") or "").strip()

    parts = [
        f"=== SUB-AGENT: {label} ===",
        task,
        "",
        "=== REQUIRED OUTPUT FORMAT ===",
        output_format or '{"output": "..."}',
    ]

    if step_index == 0:
        parts.extend(
            [
                "",
                "=== MARKET SNAPSHOT ===",
                json.dumps(market_snapshot, indent=2),
            ]
        )

    if prior_outputs:
        parts.extend(
            [
                "",
                "=== UPSTREAM PIPELINE OUTPUTS ===",
                json.dumps(prior_outputs, indent=2),
            ]
        )

    if is_last:
        parts.extend(
            [
                "",
                "=== EXECUTION RULES ===",
                "- Trade ONLY symbols listed in the market snapshot.",
                "- Only SELL symbols that appear in current_holdings.",
                "- Respect available cash for buy orders.",
                "- Use integer share quantities.",
            ]
        )

    parts.extend(["", "Return ONLY valid JSON matching the required output format."])
    return "\n".join(parts)


def pipeline_output_to_decision(parsed: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalize a pipeline step's JSON into the standard ``actions`` decision."""
    if not isinstance(parsed, dict):
        return None

    actions = parsed.get("actions")
    if isinstance(actions, list) and actions:
        return {"actions": actions}

    orders = parsed.get("orders")
    if isinstance(orders, list) and orders:
        normalized = []
        for order in orders:
            if not isinstance(order, dict):
                continue
            side = str(order.get("side") or order.get("action") or "hold").lower()
            if side not in ("buy", "sell", "hold"):
                side = "hold"
            qty = order.get("qty", order.get("quantity", order.get("position_size", 0)))
            try:
                position_size = int(qty)
            except (TypeError, ValueError):
                position_size = 0
            normalized.append(
                {
                    "action": side,
                    "symbol": order.get("symbol"),
                    "confidence": float(order.get("confidence", 0.75) or 0.75),
                    "reasoning": order.get("reason") or order.get("rationale") or "",
                    "position_size": position_size,
                    "stop_loss_price": order.get("stop_loss_price"),
                    "take_profit_price": order.get("take_profit_price"),
                }
            )
        if normalized:
            return {"actions": normalized}

    risk_actions = parsed.get("risk_actions")
    if isinstance(risk_actions, list) and risk_actions:
        normalized = []
        for risk in risk_actions:
            if not isinstance(risk, dict):
                continue
            action_type = str(risk.get("action") or "hold").lower()
            if action_type in ("stop_loss", "take_profit", "trail"):
                side = "sell"
            elif action_type == "hold":
                side = "hold"
            else:
                side = action_type if action_type in ("buy", "sell", "hold") else "hold"
            size_pct = float(risk.get("size_pct", 1.0) or 1.0)
            normalized.append(
                {
                    "action": side,
                    "symbol": risk.get("symbol"),
                    "confidence": 0.8,
                    "reasoning": risk.get("reason") or risk.get("rationale") or action_type,
                    "position_size": max(1, int(round(size_pct * 100))) if side == "sell" else 0,
                }
            )
        if normalized:
            return {"actions": normalized}

    return None


def run_pipeline_decision(
    client,
    *,
    pipeline: List[Dict[str, Any]],
    market_snapshot: Dict[str, Any],
    model: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], Tuple[int, int], int]:
    """Execute pipeline steps sequentially.

    Returns ``(decision_dict_or_none, (input_tokens, output_tokens), llm_calls)``.
    """
    if not pipeline:
        return None, (0, 0), 0

    prior_outputs: List[Dict[str, Any]] = []
    total_in = 0
    total_out = 0
    llm_calls = 0
    last_parsed: Optional[Dict[str, Any]] = None

    for index, step in enumerate(pipeline):
        if not isinstance(step, dict):
            print(f"   ⚠️  Pipeline step {index + 1} is invalid; aborting pipeline")
            return None, (total_in, total_out), llm_calls

        prompt = _build_step_prompt(
            step_index=index,
            step=step,
            market_snapshot=market_snapshot,
            prior_outputs=prior_outputs,
            is_last=(index == len(pipeline) - 1),
        )
        label = step.get("label") or f"Step {index + 1}"
        print(f"\n🔗 Pipeline step {index + 1}/{len(pipeline)}: {label}")

        response = client.messages.create(
            model=model or LLM_MODEL_NAME,
            max_tokens=DEFAULT_MAX_OUTPUT_TOKENS,
            system=PIPELINE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        llm_calls += 1
        in_delta, out_delta = extract_token_usage(response)
        total_in += in_delta
        total_out += out_delta

        parsed = parse_llm_response(extract_response_text(response))
        if parsed is None:
            print(f"   ❌ Pipeline step {index + 1} returned unparseable JSON")
            return None, (total_in, total_out), llm_calls

        prior_outputs.append(
            {
                "step": index + 1,
                "label": label,
                "presetKey": step.get("presetKey"),
                "output": parsed,
            }
        )
        last_parsed = parsed

    decision = pipeline_output_to_decision(last_parsed or {})
    if decision is None:
        print("   ❌ Final pipeline output could not be converted to trading actions")
        return None, (total_in, total_out), llm_calls

    return decision, (total_in, total_out), llm_calls
