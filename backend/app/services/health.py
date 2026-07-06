from __future__ import annotations

import os
from time import perf_counter

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.core.config import Settings
from app.infrastructure.llm.provider import LLMProvider, ProviderState
from app.schemas.health import (
    ComponentHealth,
    ComponentState,
    OllamaComponentHealth,
    SystemHealth,
)


class HealthService:
    def __init__(self, *, settings: Settings, engine: Engine, llm_provider: LLMProvider) -> None:
        self._settings = settings
        self._engine = engine
        self._llm_provider = llm_provider

    async def check(self) -> SystemHealth:
        application = ComponentHealth(
            status=ComponentState.healthy,
            detail=f"{self._settings.app_name} {self._settings.app_version}",
        )
        database = self._check_database()
        assets = self._check_assets()
        provider_health = await self._llm_provider.health()
        ollama = OllamaComponentHealth(
            status=self._map_provider_status(provider_health.status),
            base_url=provider_health.base_url,
            detail=provider_health.detail,
            latency_ms=provider_health.latency_ms,
        )

        core_healthy = (
            application.status == ComponentState.healthy
            and database.status == ComponentState.healthy
            and assets.status == ComponentState.healthy
        )
        return SystemHealth(
            status=ComponentState.healthy if core_healthy else ComponentState.degraded,
            application=application,
            database=database,
            assets=assets,
            ollama=ollama,
        )

    def _check_database(self) -> ComponentHealth:
        started = perf_counter()
        try:
            with self._engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            latency_ms = (perf_counter() - started) * 1000
            return ComponentHealth(
                status=ComponentState.healthy,
                detail="Database connection succeeded.",
                latency_ms=round(latency_ms, 2),
            )
        except Exception as exc:
            return ComponentHealth(status=ComponentState.unavailable, detail=str(exc))

    def _check_assets(self) -> ComponentHealth:
        try:
            self._settings.asset_store_path.mkdir(parents=True, exist_ok=True)
            if not os.access(self._settings.asset_store_path, os.W_OK):
                return ComponentHealth(
                    status=ComponentState.unavailable,
                    detail=f"Asset path is not writable: {self._settings.asset_store_path}",
                )
            return ComponentHealth(
                status=ComponentState.healthy,
                detail=f"Asset path is writable: {self._settings.asset_store_path}",
            )
        except OSError as exc:
            return ComponentHealth(status=ComponentState.unavailable, detail=str(exc))

    @staticmethod
    def _map_provider_status(status: ProviderState) -> ComponentState:
        if status == ProviderState.healthy:
            return ComponentState.healthy
        if status == ProviderState.unavailable:
            return ComponentState.unavailable
        return ComponentState.error
