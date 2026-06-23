import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_agents_router_exposes_the_three_routes():
    from api.v2.agents import router
    paths = sorted(r.path for r in router.routes)
    assert paths == [
        "/v2/agents",
        "/v2/agents/me",
        "/v2/agents/{agent_id}/rotate-key",
    ]
