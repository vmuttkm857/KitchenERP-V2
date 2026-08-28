from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.core.config import settings
from app.core.readiness import ReadinessService
from app.db.session import engine
from app.schemas.health import HealthResponse, ReadinessResponse


router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="kitchenerp-v2-api", version=settings.app_version)


def get_readiness_service() -> ReadinessService:
    return ReadinessService(engine)


@router.get("/ready", response_model=ReadinessResponse)
def ready(
    response: Response,
    service: Annotated[ReadinessService, Depends(get_readiness_service)],
) -> ReadinessResponse:
    result = service.check()
    if not result.ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        status="ready" if result.ready else "not_ready",
        service="kitchenerp-v2-api",
        version=settings.app_version,
        checks={
            "database": "ok" if result.database_ok else "failed",
            "schema": "ok" if result.schema_ok else "failed",
        },
    )
