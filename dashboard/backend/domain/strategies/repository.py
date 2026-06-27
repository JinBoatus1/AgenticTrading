"""On-disk JSON repository for free-form strategy prompts.

Each strategy is keyed by a short, URL-safe share ``code``. The store is a
single JSON file under the dashboard storage dir so both the API process and the
standalone Discord bot (same host) read/write the same data without a database
migration. Writes are serialized with a process-local lock and an atomic
replace; this is sufficient for the expected low write volume (a handful of
strategies created interactively).
"""

from __future__ import annotations

import json
import os
import secrets
import tempfile
import threading
from datetime import datetime, timezone
from typing import Any, Optional

from dashboard.backend.paths import DATA_DIR

STRATEGIES_FILE = DATA_DIR / "strategies.json"

_lock = threading.Lock()

# Length of the generated share code (hex chars). 8 hex chars = 32 bits, plenty
# for human-shareable, non-guessable-enough codes at this scale.
_CODE_LENGTH = 8


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load() -> dict[str, dict[str, Any]]:
    if not STRATEGIES_FILE.exists():
        return {}
    try:
        with open(STRATEGIES_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _atomic_write(data: dict[str, dict[str, Any]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix="strategies_", suffix=".json", dir=str(DATA_DIR))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, STRATEGIES_FILE)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def _new_code(existing: dict[str, Any]) -> str:
    for _ in range(20):
        code = secrets.token_hex(_CODE_LENGTH // 2)
        if code not in existing:
            return code
    # Extremely unlikely fallback: widen the space.
    return secrets.token_hex(_CODE_LENGTH)


def create_strategy(
    *,
    prompt: str,
    description: Optional[str] = None,
    source: Optional[str] = None,
    owner: Optional[str] = None,
) -> dict[str, Any]:
    """Persist a free-form strategy prompt and return the stored record.

    Args:
        prompt: the free-form strategy text the backtest agent will follow.
        description: optional short human description / original idea.
        source: where it came from (e.g. ``"discord"``, ``"web"``).
        owner: optional opaque owner id (e.g. ``"discord:<user_id>"``).
    """
    cleaned = (prompt or "").strip()
    if not cleaned:
        raise ValueError("Strategy prompt cannot be empty.")

    with _lock:
        data = _load()
        code = _new_code(data)
        record = {
            "code": code,
            "prompt": cleaned,
            "description": (description or "").strip() or None,
            "source": source or None,
            "owner": owner or None,
            "created_at": _now_iso(),
            "last_run_id": None,
            "last_run_at": None,
        }
        data[code] = record
        _atomic_write(data)
        return dict(record)


def get_strategy(code: str) -> Optional[dict[str, Any]]:
    """Return the stored strategy for ``code`` or ``None``."""
    if not code:
        return None
    with _lock:
        data = _load()
        record = data.get(code)
        return dict(record) if record else None


def set_last_run(code: str, run_id: str) -> Optional[dict[str, Any]]:
    """Attach the latest backtest run id to a strategy (best-effort)."""
    with _lock:
        data = _load()
        record = data.get(code)
        if not record:
            return None
        record["last_run_id"] = run_id
        record["last_run_at"] = _now_iso()
        data[code] = record
        _atomic_write(data)
        return dict(record)
