"""Protocol Run records.

A protocol Run (run_xxx) is the generalized successor to a Backtest. It links
an AgentVersion + environment + config to the underlying execution engine
(an external backtest session, backtest_id) and, once finalized, to the stored
result run (agent_runs.run_id, e.g. ext_...). Persisting this mapping lets the
Run API answer GET /runs/{run_id} and result/metric queries even after the
in-memory engine session is gone.

Moved verbatim (Phase 3B1) from ``dashboard/backend/run_store.py``; the original
module was removed in Phase 4A. Public class, the ``run_store`` singleton,
SQL, return schemas, and behavior are unchanged; only the module location moved.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dashboard.backend.database import DB_PATH


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _new_run_id() -> str:
    return f"run_{uuid.uuid4().hex[:12]}"


def _public_run(row: sqlite3.Row | Dict[str, Any]) -> Dict[str, Any]:
    data = dict(row)
    try:
        config = json.loads(data.get("config") or "{}")
    except (json.JSONDecodeError, TypeError):
        config = {}
    return {
        "run_id": data["run_id"],
        "agent_id": data.get("agent_id"),
        "agent_version_id": data.get("agent_version_id"),
        "session_id": data.get("session_id"),
        "environment_id": data.get("environment_id"),
        "environment_type": data.get("environment_type"),
        "config": config,
        "backtest_id": data.get("backtest_id"),
        "result_run_id": data.get("result_run_id"),
        "status": data.get("status"),
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
    }


class RunStore:
    """Persist protocol run metadata and engine/result linkage."""

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
            CREATE TABLE IF NOT EXISTS protocol_runs (
                run_id TEXT PRIMARY KEY,
                agent_id TEXT,
                agent_version_id TEXT,
                session_id TEXT NOT NULL,
                environment_id TEXT,
                environment_type TEXT,
                config TEXT NOT NULL DEFAULT '{}',
                backtest_id TEXT,
                result_run_id TEXT,
                status TEXT NOT NULL DEFAULT 'created',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_protocol_runs_agent ON protocol_runs(agent_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_protocol_runs_backtest ON protocol_runs(backtest_id)"
        )
        # protocol_steps mirrors ProtocolRun's in-memory step bookkeeping so a
        # process restart keeps historical step-id queries and idempotent
        # decision replays working (H4 follow-up). One row per step: a step has
        # at most one accepted decision, so the accepted idempotency_key and
        # its result live on the step row.
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS protocol_steps (
                run_id TEXT NOT NULL,
                step_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                timestamp TEXT,
                deadline_at TEXT,
                status TEXT NOT NULL DEFAULT 'awaiting_decision',
                idempotency_key TEXT,
                result_json TEXT,
                PRIMARY KEY (run_id, step_id),
                UNIQUE (run_id, sequence)
            )
            """
        )
        conn.commit()
        conn.close()

    def create_run(
        self,
        *,
        agent_id: Optional[str],
        agent_version_id: Optional[str],
        session_id: str,
        environment_id: str,
        environment_type: str,
        config: Dict[str, Any],
        backtest_id: Optional[str] = None,
        status: str = "created",
    ) -> Dict[str, Any]:
        run_id = _new_run_id()
        now = _utcnow_iso()
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO protocol_runs (
                run_id, agent_id, agent_version_id, session_id, environment_id,
                environment_type, config, backtest_id, result_run_id, status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                agent_id,
                agent_version_id,
                session_id,
                environment_id,
                environment_type,
                json.dumps(config or {}),
                backtest_id,
                None,
                status,
                now,
                now,
            ),
        )
        conn.commit()
        cursor.execute("SELECT * FROM protocol_runs WHERE run_id = ?", (run_id,))
        row = cursor.fetchone()
        conn.close()
        return _public_run(row)

    def update_run(
        self,
        run_id: str,
        *,
        backtest_id: Optional[str] = None,
        result_run_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> None:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE protocol_runs
            SET backtest_id = COALESCE(?, backtest_id),
                result_run_id = COALESCE(?, result_run_id),
                status = COALESCE(?, status),
                updated_at = ?
            WHERE run_id = ?
            """,
            (backtest_id, result_run_id, status, _utcnow_iso(), run_id),
        )
        conn.commit()
        conn.close()

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM protocol_runs WHERE run_id = ?", (run_id,))
        row = cursor.fetchone()
        conn.close()
        return _public_run(row) if row else None

    def list_runs(self, agent_id: str) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM protocol_runs WHERE agent_id = ? ORDER BY created_at DESC",
            (agent_id,),
        )
        rows = cursor.fetchall()
        conn.close()
        return [_public_run(row) for row in rows]

    # Runs that are still consuming resources (not yet terminal).
    _ACTIVE_STATUSES = ("created", "loading", "running")

    def count_active_runs(self, agent_id: str) -> int:
        """Number of an agent's runs that are not yet completed/failed."""
        placeholders = ",".join("?" for _ in self._ACTIVE_STATUSES)
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT COUNT(*) FROM protocol_runs "
            f"WHERE agent_id = ? AND status IN ({placeholders})",
            (agent_id, *self._ACTIVE_STATUSES),
        )
        (count,) = cursor.fetchone()
        conn.close()
        return int(count)

    def fail_unfinished_runs(self) -> int:
        """Mark runs left non-terminal by a crash/restart as failed.

        The in-memory engine session does not survive a process restart, so a
        run still marked running/loading/created can never resume — fail it so
        it stops counting against the per-agent active-run cap and reads report
        an honest terminal state. Returns the number of rows updated.
        """
        placeholders = ",".join("?" for _ in self._ACTIVE_STATUSES)
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE protocol_runs SET status = 'failed', updated_at = ? "
            f"WHERE status IN ({placeholders})",
            (_utcnow_iso(), *self._ACTIVE_STATUSES),
        )
        updated = cursor.rowcount
        conn.commit()
        conn.close()
        return int(updated)

    # -- protocol_steps: persisted step bookkeeping (H4 follow-up) ---------

    def save_step(self, run_id: str, step_id: str, sequence: int,
                  timestamp: Any = None, deadline_at: Any = None) -> None:
        """Upsert a step row when it is (re-)awaited — mirrors ensure_step_id."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO protocol_steps (run_id, step_id, sequence, timestamp,
                                        deadline_at, status)
            VALUES (?, ?, ?, ?, ?, 'awaiting_decision')
            ON CONFLICT(run_id, step_id) DO UPDATE SET
                timestamp = excluded.timestamp,
                deadline_at = excluded.deadline_at,
                status = 'awaiting_decision'
            """,
            (
                run_id,
                step_id,
                int(sequence),
                str(timestamp) if timestamp is not None else None,
                str(deadline_at) if deadline_at is not None else None,
            ),
        )
        conn.commit()
        conn.close()

    def finalize_step(self, run_id: str, step_id: str, idempotency_key: str,
                      result: Dict[str, Any]) -> None:
        """Record the step's one accepted decision — mirrors submit_decision."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE protocol_steps
            SET status = 'completed', idempotency_key = ?, result_json = ?
            WHERE run_id = ? AND step_id = ?
            """,
            (idempotency_key, json.dumps(result, default=str), run_id, step_id),
        )
        conn.commit()
        conn.close()

    def get_steps(self, run_id: str) -> List[Dict[str, Any]]:
        """All persisted steps for a run, in sequence order (result parsed)."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM protocol_steps WHERE run_id = ? ORDER BY sequence",
            (run_id,),
        )
        rows = cursor.fetchall()
        conn.close()
        steps = []
        for row in rows:
            data = dict(row)
            raw = data.pop("result_json", None)
            try:
                data["result"] = json.loads(raw) if raw else None
            except (TypeError, ValueError):
                data["result"] = None
            steps.append(data)
        return steps


run_store = RunStore()
