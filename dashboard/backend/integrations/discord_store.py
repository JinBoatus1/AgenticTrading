"""Persistent storage for Discord bot sessions and account links.

Uses the same SQLite file as backtests (``DATABASE_PATH``) unless
``DISCORD_DATABASE_URL`` is set for a dedicated Postgres connection in the
future. For MVP, SQLite is sufficient and survives bot restarts.
"""

from __future__ import annotations

import json
import os
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dashboard.backend.database import DB_PATH, enable_wal

LINK_TTL_MINUTES = 30


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _utcnow_iso() -> str:
    return _utcnow().replace(microsecond=0).isoformat()


class DiscordStore:
  """SQLite-backed Discord integration persistence."""

  def __init__(self, db_path: Path | None = None) -> None:
    self.db_path = Path(db_path or DB_PATH)
    self.db_path.parent.mkdir(parents=True, exist_ok=True)
    enable_wal(self.db_path)
    self._init_schema()

  def _conn(self) -> sqlite3.Connection:
    conn = sqlite3.connect(str(self.db_path))
    conn.row_factory = sqlite3.Row
    return conn

  def _init_schema(self) -> None:
    conn = self._conn()
    cur = conn.cursor()
    cur.execute(
      """
      CREATE TABLE IF NOT EXISTS discord_account_links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        discord_user_id TEXT NOT NULL,
        discord_username TEXT,
        atl_user_id INTEGER,
        guild_id TEXT,
        link_code TEXT UNIQUE,
        link_expires_at TEXT,
        created_at TEXT NOT NULL,
        revoked_at TEXT,
        UNIQUE(discord_user_id)
      )
      """
    )
    cur.execute(
      """
      CREATE INDEX IF NOT EXISTS idx_discord_links_code
      ON discord_account_links(link_code)
      """
    )
    cur.execute(
      """
      CREATE TABLE IF NOT EXISTS discord_dm_sessions (
        session_id TEXT PRIMARY KEY,
        discord_user_id TEXT NOT NULL UNIQUE,
        atl_user_id INTEGER,
        selected_agent_id TEXT,
        selected_agent_version_id TEXT,
        last_run_id TEXT,
        pending_backtest_json TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
      )
      """
    )
    cur.execute(
      """
      CREATE TABLE IF NOT EXISTS discord_chat_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        metadata_json TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (session_id) REFERENCES discord_dm_sessions(session_id)
      )
      """
    )
    cur.execute(
      """
      CREATE INDEX IF NOT EXISTS idx_discord_chat_session
      ON discord_chat_messages(session_id)
      """
    )
    conn.commit()
    conn.close()

  # ------------------------------------------------------------------
  # Account links
  # ------------------------------------------------------------------

  def get_link(self, discord_user_id: str) -> Optional[Dict[str, Any]]:
    conn = self._conn()
    cur = conn.cursor()
    cur.execute(
      """
      SELECT * FROM discord_account_links
      WHERE discord_user_id = ? AND revoked_at IS NULL
      """,
      (str(discord_user_id),),
    )
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

  def get_link_by_code(self, link_code: str) -> Optional[Dict[str, Any]]:
    conn = self._conn()
    cur = conn.cursor()
    cur.execute(
      """
      SELECT * FROM discord_account_links
      WHERE link_code = ? AND revoked_at IS NULL
      """,
      (link_code.strip(),),
    )
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

  def create_connect_token(
    self,
    *,
    discord_user_id: str,
    discord_username: Optional[str] = None,
    guild_id: Optional[str] = None,
  ) -> Dict[str, Any]:
    """Create or refresh a one-time connect code for a Discord user."""
    now = _utcnow_iso()
    expires = (_utcnow() + timedelta(minutes=LINK_TTL_MINUTES)).replace(microsecond=0).isoformat()
    code = secrets.token_urlsafe(24)
    existing = self.get_link(discord_user_id)
    conn = self._conn()
    cur = conn.cursor()
    if existing and existing.get("atl_user_id"):
      conn.close()
      return {
        "linked": True,
        "atl_user_id": existing["atl_user_id"],
        "discord_user_id": discord_user_id,
      }
    if existing:
      cur.execute(
        """
        UPDATE discord_account_links
        SET link_code = ?, link_expires_at = ?, discord_username = COALESCE(?, discord_username),
            guild_id = COALESCE(?, guild_id)
        WHERE discord_user_id = ?
        """,
        (code, expires, discord_username, guild_id, str(discord_user_id)),
      )
    else:
      cur.execute(
        """
        INSERT INTO discord_account_links (
          discord_user_id, discord_username, guild_id, link_code, link_expires_at, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (str(discord_user_id), discord_username, guild_id, code, expires, now),
      )
    conn.commit()
    conn.close()
    return {
      "linked": False,
      "code": code,
      "expires_at": expires,
      "discord_user_id": discord_user_id,
    }

  def confirm_link(self, *, link_code: str, atl_user_id: int) -> Dict[str, Any]:
    row = self.get_link_by_code(link_code)
    if not row:
      raise ValueError("invalid_or_expired_code")
    expires = row.get("link_expires_at")
    if expires:
      try:
        exp_dt = datetime.fromisoformat(expires)
        if exp_dt.tzinfo is None:
          exp_dt = exp_dt.replace(tzinfo=timezone.utc)
        if _utcnow() > exp_dt:
          raise ValueError("invalid_or_expired_code")
      except ValueError as exc:
        if str(exc) == "invalid_or_expired_code":
          raise
    if row.get("atl_user_id") and row["atl_user_id"] != atl_user_id:
      raise ValueError("code_already_linked")
    conn = self._conn()
    cur = conn.cursor()
    cur.execute(
      """
      UPDATE discord_account_links
      SET atl_user_id = ?, link_code = NULL, link_expires_at = NULL
      WHERE id = ?
      """,
      (atl_user_id, row["id"]),
    )
    conn.commit()
    conn.close()
    return self.get_link(row["discord_user_id"]) or {}

  def is_linked(self, discord_user_id: str) -> bool:
    link = self.get_link(discord_user_id)
    return bool(link and link.get("atl_user_id"))

  def atl_user_id_for(self, discord_user_id: str) -> Optional[int]:
    link = self.get_link(discord_user_id)
    if not link or not link.get("atl_user_id"):
      return None
    return int(link["atl_user_id"])

  # ------------------------------------------------------------------
  # DM sessions
  # ------------------------------------------------------------------

  def get_or_create_session(
    self,
    *,
    discord_user_id: str,
    atl_user_id: Optional[int] = None,
  ) -> Dict[str, Any]:
    conn = self._conn()
    cur = conn.cursor()
    cur.execute(
      "SELECT * FROM discord_dm_sessions WHERE discord_user_id = ?",
      (str(discord_user_id),),
    )
    row = cur.fetchone()
    now = _utcnow_iso()
    if row:
      session = dict(row)
      if atl_user_id and session.get("atl_user_id") != atl_user_id:
        cur.execute(
          """
          UPDATE discord_dm_sessions
          SET atl_user_id = ?, updated_at = ?
          WHERE discord_user_id = ?
          """,
          (atl_user_id, now, str(discord_user_id)),
        )
        conn.commit()
        session["atl_user_id"] = atl_user_id
      conn.close()
      return session
    session_id = str(uuid.uuid4())
    cur.execute(
      """
      INSERT INTO discord_dm_sessions (
        session_id, discord_user_id, atl_user_id, created_at, updated_at
      ) VALUES (?, ?, ?, ?, ?)
      """,
      (session_id, str(discord_user_id), atl_user_id, now, now),
    )
    conn.commit()
    conn.close()
    return {
      "session_id": session_id,
      "discord_user_id": str(discord_user_id),
      "atl_user_id": atl_user_id,
      "selected_agent_id": None,
      "selected_agent_version_id": None,
      "last_run_id": None,
      "pending_backtest_json": None,
      "created_at": now,
      "updated_at": now,
    }

  def update_session(
    self,
    discord_user_id: str,
    *,
    selected_agent_id: Any = None,
    selected_agent_version_id: Any = None,
    last_run_id: Any = None,
    pending_backtest: Any = None,
    clear_pending: bool = False,
  ) -> Dict[str, Any]:
    session = self.get_or_create_session(discord_user_id=discord_user_id)
    fields: List[str] = []
    values: List[Any] = []
    if selected_agent_id is not None:
      fields.append("selected_agent_id = ?")
      values.append(selected_agent_id)
    if selected_agent_version_id is not None:
      fields.append("selected_agent_version_id = ?")
      values.append(selected_agent_version_id)
    if last_run_id is not None:
      fields.append("last_run_id = ?")
      values.append(last_run_id)
    if pending_backtest is not None:
      fields.append("pending_backtest_json = ?")
      values.append(json.dumps(pending_backtest))
    if clear_pending:
      fields.append("pending_backtest_json = NULL")
    if not fields:
      return session
    fields.append("updated_at = ?")
    values.append(_utcnow_iso())
    values.append(str(discord_user_id))
    conn = self._conn()
    cur = conn.cursor()
    cur.execute(
      f"UPDATE discord_dm_sessions SET {', '.join(fields)} WHERE discord_user_id = ?",
      values,
    )
    conn.commit()
    conn.close()
    return self.get_or_create_session(discord_user_id=discord_user_id)

  def get_pending_backtest(self, discord_user_id: str) -> Optional[Dict[str, Any]]:
    session = self.get_or_create_session(discord_user_id=discord_user_id)
    raw = session.get("pending_backtest_json")
    if not raw:
      return None
    try:
      return json.loads(raw)
    except json.JSONDecodeError:
      return None

  # ------------------------------------------------------------------
  # Chat log (optional audit trail)
  # ------------------------------------------------------------------

  def append_message(
    self,
    *,
    session_id: str,
    role: str,
    content: str,
    metadata: Optional[Dict[str, Any]] = None,
  ) -> None:
    conn = self._conn()
    cur = conn.cursor()
    cur.execute(
      """
      INSERT INTO discord_chat_messages (session_id, role, content, metadata_json, created_at)
      VALUES (?, ?, ?, ?, ?)
      """,
      (
        session_id,
        role,
        content,
        json.dumps(metadata) if metadata else None,
        _utcnow_iso(),
      ),
    )
    conn.commit()
    conn.close()


discord_store = DiscordStore()
