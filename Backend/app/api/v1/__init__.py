from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.admin import router as admin_router
from app.api.v1.assessments import router as assessments_router
from app.api.v1.auth import router as auth_router
from app.api.v1.reports import router as reports_router
from app.api.v1.sessions import router as sessions_router
from app.api.v1.webhooks import router as webhooks_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(assessments_router)
api_router.include_router(sessions_router)
api_router.include_router(reports_router)
api_router.include_router(admin_router)
api_router.include_router(webhooks_router)

__all__: tuple[str, ...] = ("api_router",)
