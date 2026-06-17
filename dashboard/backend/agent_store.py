"""Registered external agents with persistent trading sessions and API keys."""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from database import DB_PATH


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def _new_api_key() -> str:
    return f"ag_{secrets.token_urlsafe(24)}"


def _public_agent(row: sqlite3.Row | Dict[str, Any]) -> Dict[str, Any]:
    data = dict(row)
    return {
        "agent_id": data["agent_id"],
        "name": data["name"],
        "session_id": data["session_id"],
        "model_name": data.get("model_name") or "local-model",
        "api_key_prefix": data.get("api_key_prefix") or "",
        "owner_user_id": data.get("owner_user_id"),
        "created_at": data.get("created_at"),
        "last_used_at": data.get("last_used_at"),
    }


class AgentStore:
    """Persist external agents and their trading session IDs."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = Path(db_path or DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS external_agents (
                agent_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                session_id TEXT NOT NULL UNIQUE,
                api_key_hash TEXT NOT NULL UNIQUE,
                api_key_prefix TEXT NOT NULL,
                model_name TEXT NOT NULL DEFAULT 'local-model',
                owner_user_id INTEGER,
                owner_browser_session TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used_at TIMESTAMP,
                FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE SET NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_external_agents_owner_user
            ON external_agents(owner_user_id)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_external_agents_owner_browser
            ON external_agents(owner_browser_session)
            """
        )
        conn.commit()
        conn.close()

    def create_agent(
        self,
        *,
        name: str,
        model_name: str = "local-model",
        owner_user_id: Optional[int] = None,
        owner_browser_session: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        agent_id = f"agent_{uuid.uuid4().hex[:12]}"
        session_id = session_id or str(uuid.uuid4())
        api_key = _new_api_key()
        api_key_hash = _hash_api_key(api_key)
        api_key_prefix = api_key[:12]
        now = _utcnow_iso()

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO external_agents (
                agent_id, name, session_id, api_key_hash, api_key_prefix,
                model_name, owner_user_id, owner_browser_session, created_at, last_used_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                agent_id,
                name.strip(),
                session_id,
                api_key_hash,
                api_key_prefix,
                model_name.strip() or "local-model",
                owner_user_id,
                owner_browser_session,
                now,
                now,
            ),
        )
        conn.commit()
        cursor.execute("SELECT * FROM external_agents WHERE agent_id = ?", (agent_id,))
        row = cursor.fetchone()
        conn.close()

        agent = _public_agent(row)
        agent["api_key"] = api_key
        return agent

    def register_or_get_agent(
        self,
        *,
        session_id: str,
        name: str,
        model_name: str = "local-model",
        owner_user_id: Optional[int] = None,
        owner_browser_session: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Link an existing trading session to an agent (idempotent)."""
        existing = self.get_agent_by_session(session_id)
        if existing:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE external_agents
                SET name = ?, model_name = ?, last_used_at = ?,
                    owner_user_id = COALESCE(?, owner_user_id),
                    owner_browser_session = COALESCE(?, owner_browser_session)
                WHERE session_id = ?
                """,
                (
                    name.strip(),
                    model_name.strip() or "local-model",
                    _utcnow_iso(),
                    owner_user_id,
                    owner_browser_session,
                    session_id,
                ),
            )
            conn.commit()
            conn.close()
            return self.get_agent_by_session(session_id) or existing

        return self.create_agent(
            name=name,
            model_name=model_name,
            owner_user_id=owner_user_id,
            owner_browser_session=owner_browser_session,
            session_id=session_id,
        )

    def list_agents(
        self,
        *,
        owner_user_id: Optional[int] = None,
        owner_browser_session: Optional[str] = None,
        trading_session_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        cursor = conn.cursor()
        rows: List[sqlite3.Row] = []
        seen: set = set()

        def _add_rows(query: str, params: tuple) -> None:
            cursor.execute(query, params)
            for row in cursor.fetchall():
                if row["agent_id"] not in seen:
                    seen.add(row["agent_id"])
                    rows.append(row)

        if owner_user_id is not None:
            _add_rows(
                """
                SELECT * FROM external_agents
                WHERE owner_user_id = ?
                ORDER BY created_at DESC
                """,
                (owner_user_id,),
            )
        elif owner_browser_session:
            _add_rows(
                """
                SELECT * FROM external_agents
                WHERE owner_browser_session = ?
                ORDER BY created_at DESC
                """,
                (owner_browser_session,),
            )

        if trading_session_id:
            _add_rows(
                """
                SELECT * FROM external_agents
                WHERE session_id = ?
                ORDER BY created_at DESC
                """,
                (trading_session_id,),
            )

        conn.close()
        return [_public_agent(row) for row in rows]

    def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM external_agents WHERE agent_id = ?", (agent_id,))
        row = cursor.fetchone()
        conn.close()
        return _public_agent(row) if row else None

    def get_agent_by_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM external_agents WHERE session_id = ?", (session_id,))
        row = cursor.fetchone()
        conn.close()
        return _public_agent(row) if row else None

    def resolve_api_key(self, api_key: str) -> Optional[Dict[str, Any]]:
        if not api_key or not api_key.strip():
            return None
        key_hash = _hash_api_key(api_key.strip())
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM external_agents WHERE api_key_hash = ?",
            (key_hash,),
        )
        row = cursor.fetchone()
        if row:
            cursor.execute(
                "UPDATE external_agents SET last_used_at = ? WHERE agent_id = ?",
                (_utcnow_iso(), row["agent_id"]),
            )
            conn.commit()
        conn.close()
        return _public_agent(row) if row else None

    def claim_browser_agents_to_user(
        self,
        browser_session: str,
        user_id: int,
    ) -> int:
        """Attach all browser-owned agents to a logged-in user account."""
        if not browser_session or user_id is None:
            return 0
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE external_agents
            SET owner_user_id = ?,
                owner_browser_session = COALESCE(owner_browser_session, ?),
                last_used_at = ?
            WHERE owner_browser_session = ?
              AND (owner_user_id IS NULL OR owner_user_id = ?)
            """,
            (user_id, browser_session, _utcnow_iso(), browser_session, user_id),
        )
        updated = cursor.rowcount
        conn.commit()
        conn.close()
        return updated

    def claim_agent(
        self,
        agent_id: str,
        *,
        owner_user_id: Optional[int] = None,
        owner_browser_session: Optional[str] = None,
    ) -> None:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE external_agents
            SET owner_user_id = COALESCE(?, owner_user_id),
                owner_browser_session = COALESCE(?, owner_browser_session),
                last_used_at = ?
            WHERE agent_id = ?
            """,
            (owner_user_id, owner_browser_session, _utcnow_iso(), agent_id),
        )
        conn.commit()
        conn.close()

    def rotate_api_key(self, agent_id: str) -> Optional[str]:
        """Issue a new API key for an agent. Returns the raw key once."""
        api_key = _new_api_key()
        api_key_hash = _hash_api_key(api_key)
        api_key_prefix = api_key[:12]
        now = _utcnow_iso()

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE external_agents
            SET api_key_hash = ?,
                api_key_prefix = ?,
                last_used_at = ?
            WHERE agent_id = ?
            """,
            (api_key_hash, api_key_prefix, now, agent_id),
        )
        updated = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return api_key if updated else None

    def delete_agent(self, agent_id: str) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM external_agents WHERE agent_id = ?", (agent_id,))
        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return deleted

    def owns_agent(
        self,
        agent: Dict[str, Any],
        *,
        owner_user_id: Optional[int] = None,
        owner_browser_session: Optional[str] = None,
    ) -> bool:
        if owner_user_id is not None and agent.get("owner_user_id") == owner_user_id:
            return True
        if owner_browser_session and agent.get("owner_browser_session") == owner_browser_session:
            return True
        if owner_browser_session and agent.get("session_id") == owner_browser_session:
            return True
        stored = self.get_agent(agent["agent_id"])
        if not stored:
            return False
        if owner_user_id is not None and stored.get("owner_user_id") == owner_user_id:
            return True
        if owner_browser_session and stored.get("owner_browser_session") == owner_browser_session:
            return True
        if owner_browser_session and stored.get("session_id") == owner_browser_session:
            return True
        return False


agent_store = AgentStore()
