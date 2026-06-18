from fastapi import APIRouter

from api.agents import router as agents_router
from api.algo import router as algo_router
from api.auth import router as auth_router
from api.external_backtest import router as external_backtest_router
from api.health import router as health_router

api_router = APIRouter(prefix="/api")
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(algo_router)
api_router.include_router(agents_router)
api_router.include_router(external_backtest_router)
