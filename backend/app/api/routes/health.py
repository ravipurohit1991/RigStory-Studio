from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_health_service
from app.schemas.health import SystemHealth
from app.services.health import HealthService

router = APIRouter(tags=["system"])


@router.get("/health", response_model=SystemHealth)
async def read_health(
    health_service: Annotated[HealthService, Depends(get_health_service)],
) -> SystemHealth:
    return await health_service.check()
