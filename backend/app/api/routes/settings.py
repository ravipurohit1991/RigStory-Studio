from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_app_settings
from app.core.config import Settings
from app.schemas.settings import SettingsRead

router = APIRouter(tags=["settings"])


@router.get("/settings", response_model=SettingsRead)
def read_settings(settings: Annotated[Settings, Depends(get_app_settings)]) -> SettingsRead:
    return SettingsRead(
        app_name=settings.app_name,
        app_version=settings.app_version,
        environment=settings.environment,
        api_base_path=settings.api_v1_prefix,
        asset_store_path=str(settings.asset_store_path),
        ollama_base_url=settings.ollama_base_url,
        ollama_generation_timeout_seconds=settings.ollama_generation_timeout_seconds,
        ollama_keep_alive=settings.ollama_keep_alive,
    )
