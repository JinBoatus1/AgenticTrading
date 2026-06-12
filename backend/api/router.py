from fastapi import APIRouter

from api.algo import router as algo_router
from api.auth import router as auth_router
from api.health import router as health_router

api_router = APIRouter(prefix="/api")
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(algo_router)
