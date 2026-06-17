"""
SQLite database layer for agentic trading backtesting.
Handles schema initialization and CRUD operations.

Session isolation: session_id added to agent_runs table only.
Equity timeseries and trades can be verified through agent_runs ownership.
"""

import sqlite3
import json
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Any

from paths import DEFAULT_DB_PATH

# Use persistent disk path if set (Render), otherwise local dashboard storage path
DB_PATH = Path(os.getenv("DATABASE_PATH", str(DEFAULT_DB_PATH)))


class BacktestDatabase:
    """Minimal SQLite wrapper for equity curve storage."""
    
    def __init__(self, db_path: Path = None):
        if db_path is None:
            db_path = DB_PATH
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
        self._migrate_schema()  # Handle existing DBs
    
    def _get_connection(self):
        """Get database connection."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row  # Return rows as dicts
        return conn
    
    def _init_schema(self):
        """Create tables if they don't exist (new installations)."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # agent_runs: metadata about each backtest
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_runs (
                run_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                mode TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                initial_equity REAL NOT NULL,
                final_equity REAL,
                total_return REAL,
                sharpe_ratio REAL,
                max_drawdown REAL,
                num_trades INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Index for session-scoped queries (only if table has session_id)
        try:
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_agent_runs_session 
                ON agent_runs(session_id)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_agent_runs_session_mode 
                ON agent_runs(session_id, mode)
            """)
        except Exception:
            # Indexes may fail if table exists without session_id; will be handled by migration
            pass
        
        # equity_timeseries: daily snapshots
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS equity_timeseries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                equity REAL NOT NULL,
                cash REAL NOT NULL,
                positions_value REAL NOT NULL,
                daily_return REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (run_id) REFERENCES agent_runs(run_id),
                UNIQUE(run_id, timestamp)
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_run_timestamp 
            ON equity_timeseries(run_id, timestamp)
        """)
        
        # trades: detailed trade log
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                symbol TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                side TEXT NOT NULL,
                price REAL NOT NULL,
                value REAL NOT NULL,
                reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_trades_run
            ON trades(run_id, timestamp)
        """)

        # backtest_decisions: hourly agent decisions (external + internal)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS backtest_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                step_index INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                decision_source TEXT NOT NULL,
                actions_submitted TEXT,
                actions_executed INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_decisions_run
            ON backtest_decisions(run_id, step_index)
        """)
        
        conn.commit()
        conn.close()
    
    def _migrate_schema(self):
        """Migrate existing databases: add session_id and llm_model columns if missing."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Check what columns exist
            cursor.execute("PRAGMA table_info(agent_runs)")
            columns = [row[1] for row in cursor.fetchall()]
            
            # Add session_id if missing
            if 'session_id' not in columns:
                print("🔄 Migrating: Adding session_id to agent_runs...")
                cursor.execute("""
                    ALTER TABLE agent_runs 
                    ADD COLUMN session_id TEXT DEFAULT 'legacy-demo-session'
                """)
                cursor.execute("UPDATE agent_runs SET session_id = 'legacy-demo-session' WHERE session_id IS NULL")
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_agent_runs_session 
                    ON agent_runs(session_id)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_agent_runs_session_mode 
                    ON agent_runs(session_id, mode)
                """)
                conn.commit()
                print("✅ Added session_id to agent_runs")
            
            # Add llm_model if missing (tracks which LLM was used)
            if 'llm_model' not in columns:
                print("🔄 Migrating: Adding llm_model to agent_runs...")
                cursor.execute("""
                    ALTER TABLE agent_runs 
                    ADD COLUMN llm_model TEXT DEFAULT 'rule-based'
                """)
                cursor.execute("UPDATE agent_runs SET llm_model = 'rule-based' WHERE llm_model IS NULL")
                conn.commit()
                print("✅ Added llm_model to agent_runs")
            
            if 'session_id' in columns and 'llm_model' in columns:
                print("✅ Schema up-to-date (session_id, llm_model exist)")

            self._ensure_decisions_table(cursor)
            self._migrate_trades_schema(cursor)
            conn.commit()
        
        except Exception as e:
            print(f"⚠️ Migration warning: {e}")
        
        finally:
            conn.close()

        # Trades migration is critical for external backtest finalize; retry isolated.
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            self._migrate_trades_schema(cursor)
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"⚠️ Trades migration retry warning: {e}")

    def _migrate_trades_schema(self, cursor) -> None:
        """Upgrade legacy trades table (shares/action/total_value) to new columns."""
        cursor.execute("PRAGMA table_info(trades)")
        columns = {row[1] for row in cursor.fetchall()}
        if not columns:
            return

        needed = {"quantity", "side", "value", "reason"}
        if needed.issubset(columns) and "shares" not in columns:
            return

        print("🔄 Migrating: upgrading trades table schema...")
        additions = [
            ("quantity", "INTEGER"),
            ("side", "TEXT"),
            ("value", "REAL"),
            ("reason", "TEXT"),
        ]
        for name, col_type in additions:
            if name not in columns:
                cursor.execute(f"ALTER TABLE trades ADD COLUMN {name} {col_type}")

        if "shares" in columns:
            cursor.execute("UPDATE trades SET quantity = shares WHERE quantity IS NULL")
        if "action" in columns:
            cursor.execute("UPDATE trades SET side = UPPER(action) WHERE side IS NULL")
        if "total_value" in columns:
            cursor.execute("UPDATE trades SET value = total_value WHERE value IS NULL")

        print("✅ trades table migrated (quantity, side, value, reason)")

    def _ensure_decisions_table(self, cursor) -> None:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS backtest_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                step_index INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                decision_source TEXT NOT NULL,
                actions_submitted TEXT,
                actions_executed INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_decisions_run
            ON backtest_decisions(run_id, step_index)
        """)

    def _trades_column_set(self, cursor) -> set:
        cursor.execute("PRAGMA table_info(trades)")
        return {row[1] for row in cursor.fetchall()}
    
    def insert_run(self, run_id: str, session_id: str, agent_name: str, mode: str, 
                   start_date: str, end_date: str, 
                   initial_equity: float,
                   final_equity: Optional[float] = None,
                   total_return: Optional[float] = None,
                   sharpe_ratio: Optional[float] = None,
                   max_drawdown: Optional[float] = None,
                   num_trades: int = 0,
                   llm_model: str = "rule-based") -> None:
        """Insert a new backtest run with session_id and LLM model tracking."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO agent_runs 
            (run_id, session_id, agent_name, mode, start_date, end_date, 
             initial_equity, final_equity, total_return, sharpe_ratio, 
             max_drawdown, num_trades, llm_model)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (run_id, session_id, agent_name, mode, start_date, end_date,
              initial_equity, final_equity, total_return, sharpe_ratio,
              max_drawdown, num_trades, llm_model))
        
        conn.commit()
        conn.close()
    
    def insert_equity_point(self, run_id: str, timestamp: str, 
                          equity: float, cash: float, 
                          positions_value: float,
                          daily_return: Optional[float] = None) -> None:
        """Insert a single equity data point."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO equity_timeseries 
            (run_id, timestamp, equity, cash, positions_value, daily_return)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (run_id, timestamp, equity, cash, positions_value, daily_return))
        
        conn.commit()
        conn.close()
    
    def insert_equity_points(self, run_id: str, 
                           points: List[Dict[str, Any]]) -> None:
        """Batch insert equity points. 
        
        Each point should have: timestamp, equity, cash, positions_value, [daily_return]
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        for point in points:
            cursor.execute("""
                INSERT OR REPLACE INTO equity_timeseries 
                (run_id, timestamp, equity, cash, positions_value, daily_return)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                run_id,
                point['timestamp'],
                point['equity'],
                point['cash'],
                point['positions_value'],
                point.get('daily_return')
            ))
        
        conn.commit()
        conn.close()
    
    def get_all_runs(self) -> List[Dict]:
        """Get metadata for all runs."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM agent_runs ORDER BY created_at DESC")
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_runs_by_session(self, session_id: str) -> List[Dict]:
        """Get all runs for a specific session."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM agent_runs 
            WHERE session_id = ?
            ORDER BY created_at DESC
        """, (session_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_run(self, run_id: str) -> Optional[Dict]:
        """Get metadata for a specific run (no session check)."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM agent_runs WHERE run_id = ?", (run_id,))
        row = cursor.fetchone()
        conn.close()
        
        return dict(row) if row else None
    
    def get_run_with_session(self, run_id: str, session_id: str) -> Optional[Dict]:
        """Get a run, verifying it belongs to the session."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM agent_runs 
            WHERE run_id = ? AND session_id = ?
        """, (run_id, session_id))
        row = cursor.fetchone()
        conn.close()
        
        return dict(row) if row else None
    
    def get_equity_curve(self, run_id: str) -> List[Dict]:
        """Get full equity curve for a run."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT timestamp, equity, cash, positions_value, daily_return 
            FROM equity_timeseries 
            WHERE run_id = ?
            ORDER BY timestamp ASC
        """, (run_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_equity_curves(self, run_ids: List[str]) -> Dict[str, List[Dict]]:
        """Get equity curves for multiple runs."""
        result = {}
        for run_id in run_ids:
            result[run_id] = self.get_equity_curve(run_id)
        return result
    
    def get_runs_by_mode(self, mode: str) -> List[Dict]:
        """Get all runs for a specific mode ('backtest' or 'paper')."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM agent_runs 
            WHERE mode = ?
            ORDER BY created_at DESC
        """, (mode,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]

    def insert_trades(self, run_id: str, trades: List[Dict[str, Any]]) -> None:
        """Batch insert trade records for a backtest run."""
        if not trades:
            return
        conn = self._get_connection()
        cursor = conn.cursor()
        self._migrate_trades_schema(cursor)
        conn.commit()
        columns = self._trades_column_set(cursor)
        for trade in trades:
            ts = trade.get("timestamp")
            if hasattr(ts, "isoformat"):
                ts = ts.isoformat()
            side = str(trade.get("side", "")).upper()
            qty = int(trade.get("shares") or trade.get("quantity") or 0)
            price = float(trade.get("price") or 0)
            value = float(trade.get("cost") or trade.get("proceeds") or trade.get("value") or qty * price)

            if "quantity" in columns:
                col_names = ["run_id", "timestamp", "symbol", "quantity", "side", "price", "value"]
                col_values = [run_id, str(ts), trade.get("symbol"), qty, side, price, value]
                if "reason" in columns:
                    col_names.append("reason")
                    col_values.append(trade.get("reason"))
                # Legacy columns may still be NOT NULL after migration
                if "action" in columns:
                    col_names.extend(["action", "shares", "total_value"])
                    col_values.extend([side, qty, value])
                placeholders = ", ".join("?" for _ in col_names)
                cursor.execute(
                    f"INSERT INTO trades ({', '.join(col_names)}) VALUES ({placeholders})",
                    col_values,
                )
            elif "shares" in columns:
                cursor.execute("""
                    INSERT INTO trades
                    (run_id, timestamp, symbol, action, shares, price, total_value)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    run_id,
                    str(ts),
                    trade.get("symbol"),
                    side,
                    qty,
                    price,
                    value,
                ))
            else:
                raise RuntimeError("trades table has unsupported schema")
        conn.commit()
        conn.close()

    def insert_decisions(self, run_id: str, decisions: List[Dict[str, Any]]) -> None:
        """Batch insert hourly decision log entries."""
        if not decisions:
            return
        conn = self._get_connection()
        cursor = conn.cursor()
        self._ensure_decisions_table(cursor)
        conn.commit()
        for entry in decisions:
            cursor.execute("""
                INSERT INTO backtest_decisions
                (run_id, step_index, timestamp, decision_source, actions_submitted, actions_executed)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                run_id,
                entry.get("step_index", 0),
                entry.get("timestamp"),
                entry.get("decision_source"),
                json.dumps(entry.get("actions_submitted") or []),
                entry.get("actions_executed", 0),
            ))
        conn.commit()
        conn.close()

    def get_trades(self, run_id: str) -> List[Dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        columns = self._trades_column_set(cursor)
        if "quantity" in columns:
            cursor.execute("""
                SELECT timestamp, symbol, quantity, side, price, value, reason
                FROM trades WHERE run_id = ?
                ORDER BY timestamp ASC, id ASC
            """, (run_id,))
        else:
            cursor.execute("""
                SELECT timestamp, symbol, shares AS quantity, action AS side,
                       price, total_value AS value
                FROM trades WHERE run_id = ?
                ORDER BY timestamp ASC, id ASC
            """, (run_id,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_decisions(self, run_id: str) -> List[Dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT step_index, timestamp, decision_source, actions_submitted, actions_executed
            FROM backtest_decisions WHERE run_id = ?
            ORDER BY step_index ASC
        """, (run_id,))
        rows = cursor.fetchall()
        conn.close()
        result = []
        for row in rows:
            item = dict(row)
            try:
                item["actions_submitted"] = json.loads(item.get("actions_submitted") or "[]")
            except json.JSONDecodeError:
                item["actions_submitted"] = []
            result.append(item)
        return result
    
    def delete_run(self, run_id: str) -> None:
        """Delete a run and all its data."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM equity_timeseries WHERE run_id = ?", (run_id,))
        cursor.execute("DELETE FROM trades WHERE run_id = ?", (run_id,))
        cursor.execute("DELETE FROM backtest_decisions WHERE run_id = ?", (run_id,))
        cursor.execute("DELETE FROM agent_runs WHERE run_id = ?", (run_id,))
        
        conn.commit()
        conn.close()
    
    def clear_all(self) -> None:
        """Clear all data (useful for testing)."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM equity_timeseries")
        cursor.execute("DELETE FROM trades")
        cursor.execute("DELETE FROM backtest_decisions")
        cursor.execute("DELETE FROM agent_runs")
        
        conn.commit()
        conn.close()


# Singleton instance
db = BacktestDatabase()
