"""POST /paper/start-session must actually record the run (CodeQL py/call/wrong-arguments #67).

``BacktestDatabase.insert_run`` requires ``session_id``; the route omitted it,
so every credentialed start-session raised ``TypeError`` — swallowed by the
``except Exception`` envelope into ``{"success": False}``. The endpoint could
never have succeeded; it only ever ran with live Alpaca credentials, which is
why nothing caught it.
"""

from fastapi.testclient import TestClient

from dashboard.backend.app import app
from dashboard.backend.api.routers import paper_trading as paper_mod
from dashboard.backend.database import db

client = TestClient(app)


class _FakeAlpacaClient:
    def get_account(self):
        return {"equity": 55555.0, "cash": 55555.0}


def test_start_session_succeeds_and_records_run(monkeypatch):
    monkeypatch.setattr(paper_mod, "AlpacaPaperTradingClient", _FakeAlpacaClient)
    data = client.post(
        "/paper/start-session", params={"agent_name": "guard-test"}
    ).json()
    assert data["success"] is True, data
    assert data["initial_equity"] == 55555.0
    run = db.get_run(data["run_id"])
    assert run is not None
    assert run["mode"] == "paper"
    assert run["agent_name"] == "guard-test"
