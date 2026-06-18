"""
Negative tests for backtest session isolation.
Uses a temporary test database.
"""

import pytest
import tempfile
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from app import app
from database import BacktestDatabase
import uuid

@pytest.fixture
def temp_db():
    """Create a temporary test database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        test_db = BacktestDatabase(db_path=db_path)
        yield test_db
        # Cleanup happens automatically when tmpdir is deleted

@pytest.fixture
def client(temp_db, monkeypatch):
    """Test client with temporary database."""
    # Patch the database module to use temp DB
    import app as app_module
    import database as db_module
    
    monkeypatch.setattr(app_module, "db", temp_db)
    monkeypatch.setattr(db_module, "db", temp_db)
    
    return TestClient(app)

def test_session_isolation_backtest_list(client, temp_db):
    """Session B should not see Session A's backtests."""
    
    session_a = str(uuid.uuid4())
    session_b = str(uuid.uuid4())
    run_a = str(uuid.uuid4())
    run_b = str(uuid.uuid4())
    
    # Create backtest in Session A
    temp_db.insert_run(
        run_id=run_a,
        session_id=session_a,
        agent_name="Agent A",
        mode="backtest",
        start_date="2024-01-01",
        end_date="2024-01-31",
        initial_equity=100000
    )
    
    # Create backtest in Session B
    temp_db.insert_run(
        run_id=run_b,
        session_id=session_b,
        agent_name="Agent B",
        mode="backtest",
        start_date="2024-01-01",
        end_date="2024-01-31",
        initial_equity=100000
    )
    
    # Session A lists backtests: should only see its own
    response_a = client.get('/runs', headers={'X-Session-Id': session_a})
    assert response_a.status_code == 200
    runs_a = response_a.json()
    assert len(runs_a) == 1
    assert runs_a[0]['agent_name'] == "Agent A"
    
    # Session B lists backtests: should only see its own
    response_b = client.get('/runs', headers={'X-Session-Id': session_b})
    assert response_b.status_code == 200
    runs_b = response_b.json()
    assert len(runs_b) == 1
    assert runs_b[0]['agent_name'] == "Agent B"
    
    print("✅ Session isolation: Each session sees only its own backtests")

def test_session_cannot_access_other_backtest(client, temp_db):
    """Session A should get 404 when accessing Session B's run_id."""
    
    session_a = str(uuid.uuid4())
    session_b = str(uuid.uuid4())
    run_id_b = str(uuid.uuid4())
    
    # Create backtest in Session B
    temp_db.insert_run(
        run_id=run_id_b,
        session_id=session_b,
        agent_name="Agent B",
        mode="backtest",
        start_date="2024-01-01",
        end_date="2024-01-31",
        initial_equity=100000
    )
    
    # Session A tries to access run from Session B: should get 404
    response_a = client.get(
        f'/runs/{run_id_b}',
        headers={'X-Session-Id': session_a}
    )
    assert response_a.status_code == 404

def test_latest_run_is_session_specific(client, temp_db):
    """latest-run should return only this session's latest backtest."""
    import time
    
    session_a = str(uuid.uuid4())
    session_b = str(uuid.uuid4())
    run_id_a1 = str(uuid.uuid4())
    run_id_a2 = str(uuid.uuid4())
    run_id_b = str(uuid.uuid4())
    
    # Create 2 backtests in Session A (with 1+ second delay to ensure different timestamps)
    temp_db.insert_run(
        run_id=run_id_a1,
        session_id=session_a,
        agent_name="Agent A",
        mode="backtest",
        start_date="2024-01-01",
        end_date="2024-01-31",
        initial_equity=100000
    )
    time.sleep(1.1)  # Ensure different second (SQLite CURRENT_TIMESTAMP has second precision)
    temp_db.insert_run(
        run_id=run_id_a2,
        session_id=session_a,
        agent_name="Agent A",
        mode="backtest",
        start_date="2024-02-01",
        end_date="2024-02-28",
        initial_equity=100000
    )
    
    # Create 1 backtest in Session B
    temp_db.insert_run(
        run_id=run_id_b,
        session_id=session_b,
        agent_name="Agent B",
        mode="backtest",
        start_date="2024-01-01",
        end_date="2024-01-31",
        initial_equity=100000
    )
    
    # Session A's latest-run should return a2
    response_a = client.get('/runs/latest/metrics', headers={'X-Session-Id': session_a})
    assert response_a.status_code == 200
    assert response_a.json()['run_id'] == run_id_a2
    
    # Session B's latest-run should return b
    response_b = client.get('/runs/latest/metrics', headers={'X-Session-Id': session_b})
    assert response_b.status_code == 200
    assert response_b.json()['run_id'] == run_id_b

def test_missing_session_header_rejected(client):
    """Backtest endpoints should reject missing X-Session-Id."""
    response = client.get('/runs')
    assert response.status_code == 400
    assert 'Missing X-Session-Id' in str(response.json())

def test_invalid_session_id_rejected(client):
    """Invalid session ID should be rejected."""
    response = client.get('/runs', headers={'X-Session-Id': 'not-a-uuid'})
    assert response.status_code == 400
    assert 'Invalid' in str(response.json())

def test_paper_trading_no_session_required(client):
    """Paper trading routes should NOT require X-Session-Id."""
    # Should not return 400 for missing header
    response = client.get('/paper/account')
    assert response.status_code != 400
