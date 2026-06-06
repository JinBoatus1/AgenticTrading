from fastapi import APIRouter

from api.auth import router as auth_router
from api.health import router as health_router

api_router = APIRouter(prefix="/api")
api_router.include_router(health_router)
api_router.include_router(auth_router)
