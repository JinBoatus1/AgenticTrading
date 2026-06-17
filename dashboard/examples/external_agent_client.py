#!/usr/bin/env python3
"""
Minimal external-agent backtest client.

Uses simple RSI rules (no LLM required). Point at your API server and reuse
the dashboard session id so results appear on the website.

Usage:
  export SESSION_ID=$(python3 -c "import uuid; print(uuid.uuid4())")
  python3 examples/external_agent_client.py \\
    --api http://localhost:8000 \\
    --session-id "$SESSION_ID" \\
    --start 2026-04-15 --end 2026-04-16

  # Paste SESSION_ID into browser console:
  # localStorage.setItem('trading-session-id', '<SESSION_ID>'); location.reload();
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request


def api_request(
    method: str,
    url: str,
    session_id: str,
    body: dict | None = None,
) -> dict:
    data = None
    headers = {
        "X-Session-Id": session_id,
        "Accept": "application/json",
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        if exc.code == 409:
            try:
                return json.loads(detail).get("detail", json.loads(detail))
            except json.JSONDecodeError:
                pass
        try:
            parsed = json.loads(detail)
            if isinstance(parsed, dict) and "detail" in parsed:
                detail = parsed["detail"]
        except json.JSONDecodeError:
            pass
        raise RuntimeError(f"HTTP {exc.code} {url}: {detail}") from exc


def rule_based_decision(snapshot: dict) -> dict:
    """Demo agent: buy oversold, sell overbought, else hold."""
    actions = []
    holdings = snapshot.get("current_holdings") or {}
    signals = snapshot.get("top_signals") or {}

    for symbol, sig in signals.items():
        rsi = float(sig.get("rsi") or 50)
        price = float(sig.get("price") or 0)
        if price <= 0:
            continue

        owned = symbol in holdings and holdings[symbol].get("shares", 0) > 0

        if not owned and rsi < 35:
            shares = max(1, int(2000 / price))
            actions.append({
                "action": "buy",
                "symbol": symbol,
                "confidence": 0.75,
                "reasoning": "RSI oversold entry",
                "position_size": shares,
                "stop_loss_price": None,
                "take_profit_price": None,
            })
        elif owned and rsi > 65:
            actions.append({
                "action": "sell",
                "symbol": symbol,
                "confidence": 0.8,
                "reasoning": "RSI overbought exit",
                "position_size": holdings[symbol]["shares"],
                "stop_loss_price": None,
                "take_profit_price": None,
            })

    if not actions:
        actions.append({
            "action": "hold",
            "symbol": next(iter(signals), "AAPL"),
            "confidence": 0.5,
            "reasoning": "No signal this hour",
            "position_size": 0,
            "stop_loss_price": None,
            "take_profit_price": None,
        })

    return {"actions": actions}


def main() -> int:
    parser = argparse.ArgumentParser(description="External agent backtest client (demo)")
    parser.add_argument("--api", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--session-id", required=True, help="X-Session-Id (match dashboard)")
    parser.add_argument("--agent-name", default="my-local-agent")
    parser.add_argument("--model-name", default="rule-based-demo")
    parser.add_argument("--start", default="2026-04-15")
    parser.add_argument("--end", default="2026-04-16")
    args = parser.parse_args()

    base = args.api.rstrip("/")

    print(f"Session: {args.session_id}")
    print("Dashboard: localStorage.setItem('trading-session-id', '<SESSION>'); location.reload();")
    print()

    try:
        schema = api_request("GET", f"{base}/api/v1/backtest/schema", args.session_id)
        print(f"Decision timeout: {schema.get('decision_timeout_seconds')}s")
    except RuntimeError as exc:
        print(f"Warning: could not fetch schema ({exc})")

    started = api_request(
        "POST",
        f"{base}/api/v1/backtest/start",
        args.session_id,
        {
            "start_date": args.start,
            "end_date": args.end,
            "agent_name": args.agent_name,
            "model_name": args.model_name,
            "mode": "safe_trading",
        },
    )
    backtest_id = started["backtest_id"]
    total = started["total_steps"]
    print(f"Started backtest {backtest_id} ({total} steps)")

    step_num = 0
    while True:
        ctx = api_request(
            "GET",
            f"{base}/api/v1/backtest/{backtest_id}/steps/current",
            args.session_id,
        )
        status = ctx.get("status")

        if status == "completed":
            print("\nDone!")
            run_id = ctx.get("run_id")
            compare_path = ctx.get("compare_url")
            print(json.dumps(ctx, indent=2))
            if compare_path:
                print(f"\nEquity chart: {base}{compare_path}")
            if run_id:
                try:
                    summary = api_request(
                        "GET",
                        f"{base}/api/v1/backtest/runs/{run_id}/result",
                        args.session_id,
                    )
                    print(f"\nTrades: {len(summary.get('trades', []))}")
                    print(f"Decisions: {len(summary.get('decisions', []))}")
                except RuntimeError as exc:
                    print(f"Result fetch: {exc}")
            print(f"\nWebsite session:\n  localStorage.setItem('trading-session-id', '{args.session_id}'); location.reload();")
            return 0

        if status == "failed":
            print("Backtest failed:", ctx.get("error"))
            return 1

        if status != "waiting_decision":
            time.sleep(0.5)
            continue

        step_num = ctx.get("step_index", 0) + 1
        deadline = ctx.get("decision_deadline_at", "")
        print(f"Step {step_num}/{total} deadline={deadline}")

        payload = rule_based_decision(ctx.get("market_snapshot") or {})
        result = api_request(
            "POST",
            f"{base}/api/v1/backtest/{backtest_id}/steps/current/decisions",
            args.session_id,
            payload,
        )
        if isinstance(result, dict) and result.get("error") == "step_already_closed":
            print("  Step closed (timeout), continuing...")
            continue
        if not result.get("accepted"):
            print("  Decision rejected:", result)
        else:
            executed = result.get("executed") or []
            print(f"  Executed {result.get('executed_count', 0)} action(s)")
            for item in executed:
                print(f"    {item.get('action', '').upper()} {item.get('symbol')} x{item.get('shares')}")
            if result.get("status") == "completed" and result.get("compare_url"):
                print(f"\nCompleted early. Chart: {base}{result['compare_url']}")
                return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
