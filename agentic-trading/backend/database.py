"""
SQLite database layer for agentic trading backtesting.
Handles schema initialization and CRUD operations.
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Any

DB_PATH = Path(__file__).parent.parent / "data" / "backtest.db"


class BacktestDatabase:
    """Minimal SQLite wrapper for equity curve storage."""
    
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
    
    def _get_connection(self):
        """Get database connection."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row  # Return rows as dicts
        return conn
    
    def _init_schema(self):
        """Create tables if they don't exist."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # agent_runs: metadata about each backtest
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_runs (
                run_id TEXT PRIMARY KEY,
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
        
        # Index for fast lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_run_timestamp 
            ON equity_timeseries(run_id, timestamp)
        """)
        
        # trades: detailed trade log (optional, for later)
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
        
        conn.commit()
        conn.close()
    
    def insert_run(self, run_id: str, agent_name: str, mode: str, 
                   start_date: str, end_date: str, 
                   initial_equity: float,
                   final_equity: Optional[float] = None,
                   total_return: Optional[float] = None,
                   sharpe_ratio: Optional[float] = None,
                   max_drawdown: Optional[float] = None,
                   num_trades: int = 0) -> None:
        """Insert a new backtest run."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO agent_runs 
            (run_id, agent_name, mode, start_date, end_date, 
             initial_equity, final_equity, total_return, sharpe_ratio, 
             max_drawdown, num_trades)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (run_id, agent_name, mode, start_date, end_date,
              initial_equity, final_equity, total_return, sharpe_ratio,
              max_drawdown, num_trades))
        
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
        
        cursor.execute("""
            SELECT * FROM agent_runs 
            ORDER BY created_at DESC
        """)
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_run(self, run_id: str) -> Optional[Dict]:
        """Get metadata for a specific run."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM agent_runs WHERE run_id = ?", (run_id,))
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
    
    def delete_run(self, run_id: str) -> None:
        """Delete a run and all its data."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM equity_timeseries WHERE run_id = ?", (run_id,))
        cursor.execute("DELETE FROM trades WHERE run_id = ?", (run_id,))
        cursor.execute("DELETE FROM agent_runs WHERE run_id = ?", (run_id,))
        
        conn.commit()
        conn.close()
    
    def clear_all(self) -> None:
        """Clear all data (useful for testing)."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM equity_timeseries")
        cursor.execute("DELETE FROM trades")
        cursor.execute("DELETE FROM agent_runs")
        
        conn.commit()
        conn.close()


# Singleton instance
db = BacktestDatabase()
