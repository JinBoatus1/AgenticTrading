"""Agentic Trading Lab - lightweight Python client.

Agentic Trading Lab is an open-source experimental playground for LLM-powered
trading agents: prototype agents, run backtests and paper-trading simulations,
inspect reasoning and decision logs, and benchmark against market baselines.

This package provides a small, dependency-free client for the Agentic Trading
Lab REST API so you can drive backtests and read results from Python.

Links:
  - Live demo: https://agentic-trading-lab.vercel.app/
  - Docs:      https://finagent-orchestration.readthedocs.io/
  - Source:    https://github.com/Allan-Feng/AgenticTrading
"""

from __future__ import annotations

from .client import AgenticTradingClient, ApiError

__all__ = [
    "AgenticTradingClient",
    "ApiError",
    "__version__",
    "info",
]

__version__ = "0.1.0"

LIVE_DEMO_URL = "https://agentic-trading-lab.vercel.app/"
DOCS_URL = "https://finagent-orchestration.readthedocs.io/"
SOURCE_URL = "https://github.com/Allan-Feng/AgenticTrading"


def info() -> dict:
    """Return basic package/project metadata as a dict."""
    return {
        "name": "agentictrading",
        "version": __version__,
        "summary": "Lightweight Python client for the Agentic Trading Lab REST API.",
        "live_demo": LIVE_DEMO_URL,
        "docs": DOCS_URL,
        "source": SOURCE_URL,
    }
