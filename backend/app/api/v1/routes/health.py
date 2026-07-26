"""Health / liveness endpoint."""

from fastapi import APIRouter

from app.core.config import settings
from app.schemas.common import HealthStatus

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthStatus, summary="Liveness probe")
async def health() -> HealthStatus:
    return HealthStatus(
        status="ok",
        service=settings.app_name,
        environment=settings.environment,
    )
