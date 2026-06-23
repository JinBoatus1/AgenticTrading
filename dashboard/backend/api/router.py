from fastapi import APIRouter

from dashboard.backend.api.routers.agent_versions import router as agent_versions_router
from dashboard.backend.api.routers.agents import router as agents_router
from dashboard.backend.api.routers.algo import router as algo_router
from dashboard.backend.api.auth import router as auth_router
from dashboard.backend.api.routers.environments import router as environments_router
from dashboard.backend.api.routers.external_backtest import router as external_backtest_router
from dashboard.backend.api.health import router as health_router
from dashboard.backend.api.routers.leaderboard import router as leaderboard_router
from dashboard.backend.api.routers.runs import router as runs_router

api_router = APIRouter(prefix="/api")
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(algo_router)
api_router.include_router(agents_router)
api_router.include_router(agent_versions_router)
api_router.include_router(external_backtest_router)
api_router.include_router(runs_router)
api_router.include_router(environments_router)
api_router.include_router(leaderboard_router)
