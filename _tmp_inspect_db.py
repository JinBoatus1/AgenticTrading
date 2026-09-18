import sqlite3
from pathlib import Path

db = Path("dashboard/storage/data/backtest.db")
c = sqlite3.connect(db)
tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print("tables:", tables)
if "users" in tables:
    print("users cols:", list(c.execute("PRAGMA table_info(users)")))
    print("user rows:", c.execute("SELECT * FROM users").fetchall())
else:
    print("no users table")
for name in ("auth_sessions", "user_entitlements", "email_change_requests"):
    if name in tables:
        print(name, "count:", c.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0])
