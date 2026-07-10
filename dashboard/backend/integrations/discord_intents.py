"""Keyword-based intent router for Discord DM messages."""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_BACKTEST_START = "2026-06-01"
DEFAULT_BACKTEST_END = "2026-06-30"

MAG7_SYMBOLS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META"]
TOP10_SYMBOLS = ["AAPL", "MSFT", "JPM", "V", "JNJ", "WMT", "PG", "MA", "HD", "DIS"]

INTENT_SHOW_AGENTS = "show_agents"
INTENT_SELECT_AGENT = "select_agent"
INTENT_RUN_BACKTEST = "run_backtest"
INTENT_CHECK_STATUS = "check_status"
INTENT_CONNECT = "connect"
INTENT_HELP = "help"
INTENT_UNKNOWN = "unknown"

_SHOW_AGENTS_PHRASES = (
  "show my agents",
  "list agents",
  "what agents do i have",
  "my agents",
  "show agents",
)

_SELECT_AGENT_RE = re.compile(
  r"^(?:use|select|switch to|pick)\s+(?:my\s+)?(.+?)(?:\s+agent)?$",
  re.IGNORECASE,
)

_RUN_BACKTEST_PHRASES = (
  "run backtest",
  "run a backtest",
  "start backtest",
  "test my agent",
  "backtest on",
  "backtest for",
)

_STATUS_PHRASES = (
  "status",
  "is it done",
  "latest run",
  "run status",
  "check status",
  "how is my backtest",
)

_HELP_PHRASES = ("help", "what can you do", "commands", "how do i use")

_CONNECT_PHRASES = (
  "i want to connect",
  "want to connect",
  "link my account",
  "link account",
  "connect my account",
  "connect account",
  "how do i connect",
  "how to connect",
  "atl connect",
)

_SYMBOL_RE = re.compile(r"\b[A-Z]{1,5}\b")
_DATE_RANGE_RE = re.compile(
  r"(?:from\s+)?(\d{4}-\d{2}-\d{2})\s+(?:to|through|-)\s+(\d{4}-\d{2}-\d{2})",
  re.IGNORECASE,
)
_MONTH_DAY_RE = re.compile(
  r"(?:from\s+)?([A-Za-z]+)\s+(\d{1,2})\s+(?:to|-)\s+([A-Za-z]+)\s+(\d{1,2})",
  re.IGNORECASE,
)


@dataclass
class RoutedIntent:
  intent: str
  agent_query: Optional[str] = None
  backtest: Dict[str, Any] = field(default_factory=dict)


def _normalize(text: str) -> str:
  return re.sub(r"\s+", " ", text.strip().lower())


def _month_name_to_num(name: str) -> Optional[int]:
  name = name.strip().lower()[:3]
  for i, month in enumerate(calendar.month_abbr):
    if month and month.lower() == name:
      return i
  for i, month in enumerate(calendar.month_name):
    if month and month.lower().startswith(name):
      return i
  return None


def _last_month_range(today: Optional[date] = None) -> Tuple[str, str]:
  today = today or date.today()
  first_this = today.replace(day=1)
  last_prev = first_this - timedelta(days=1)
  first_prev = last_prev.replace(day=1)
  return first_prev.isoformat(), last_prev.isoformat()


def parse_symbols(text: str) -> List[str]:
  normalized = text.lower()
  if "magnificent 7" in normalized or "mag 7" in normalized or "mag7" in normalized:
    return list(MAG7_SYMBOLS)
  if "top 10" in normalized or "top10" in normalized or "djia top" in normalized:
    return list(TOP10_SYMBOLS)
  found = _SYMBOL_RE.findall(text.upper())
  # Filter common English words that look like tickers
  stop = {"I", "A", "AM", "PM", "US", "UK", "AI", "ID", "OR", "ON", "TO", "MY", "RUN", "FROM"}
  return [s for s in found if s not in stop]


def parse_date_range(text: str, *, today: Optional[date] = None) -> Tuple[Optional[str], Optional[str]]:
  today = today or date.today()
  normalized = _normalize(text)
  if "last month" in normalized:
    return _last_month_range(today)
  m = _DATE_RANGE_RE.search(text)
  if m:
    return m.group(1), m.group(2)
  m = _MONTH_DAY_RE.search(text)
  if m:
    m1 = _month_name_to_num(m.group(1))
    m2 = _month_name_to_num(m.group(3))
    if m1 and m2:
      year = today.year
      try:
        start = date(year, m1, int(m.group(2)))
        end = date(year, m2, int(m.group(4)))
        if end < start:
          start, end = end, start
        return start.isoformat(), end.isoformat()
      except ValueError:
        pass
  return None, None


def parse_backtest_config(text: str) -> Dict[str, Any]:
  symbols = parse_symbols(text)
  start, end = parse_date_range(text)
  return {
    "symbols": symbols,
    "start_date": start,
    "end_date": end,
    "initial_capital": 100_000,
  }


def route_intent(text: str) -> RoutedIntent:
  normalized = _normalize(text)
  if not normalized:
    return RoutedIntent(intent=INTENT_UNKNOWN)

  if any(p in normalized for p in _HELP_PHRASES):
    return RoutedIntent(intent=INTENT_HELP)

  if normalized == "connect" or any(p in normalized for p in _CONNECT_PHRASES):
    return RoutedIntent(intent=INTENT_CONNECT)

  if any(p in normalized for p in _SHOW_AGENTS_PHRASES):
    return RoutedIntent(intent=INTENT_SHOW_AGENTS)

  if any(p in normalized for p in _STATUS_PHRASES):
    return RoutedIntent(intent=INTENT_CHECK_STATUS)

  m = _SELECT_AGENT_RE.match(text.strip())
  if m:
    return RoutedIntent(intent=INTENT_SELECT_AGENT, agent_query=m.group(1).strip())

  if any(p in normalized for p in _RUN_BACKTEST_PHRASES) or normalized.startswith("backtest"):
    return RoutedIntent(
      intent=INTENT_RUN_BACKTEST,
      backtest=parse_backtest_config(text),
    )

  return RoutedIntent(intent=INTENT_UNKNOWN)


def help_message() -> str:
  return (
    "**ATL Discord agent** — try messages like:\n"
    "• `show my agents`\n"
    "• `use momentum agent`\n"
    "• `run backtest on AAPL MSFT last month`\n"
    "• `status` or `latest run`\n"
    "• `connect` — link your ATL website account\n\n"
    "Not linked yet? Just say **connect**."
  )


def format_backtest_confirmation(
  *,
  agent_name: str,
  symbols: List[str],
  start_date: str,
  end_date: str,
  initial_capital: int = 100_000,
) -> str:
  sym = ", ".join(symbols) if symbols else "(default universe)"
  return (
    f"**Ready to run backtest:**\n"
    f"**Agent:** {agent_name}\n"
    f"**Symbols:** {sym}\n"
    f"**Period:** {start_date} to {end_date}\n"
    f"**Initial Capital:** ${initial_capital:,}"
  )
