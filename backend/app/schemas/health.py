from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class ComponentState(StrEnum):
    healthy = "healthy"
    degraded = "degraded"
    unavailable = "unavailable"
    error = "error"


class ComponentHealth(BaseModel):
    status: ComponentState
    detail: str | None = None
    latency_ms: float | None = None

    model_config = ConfigDict(frozen=True)


class OllamaComponentHealth(ComponentHealth):
    base_url: str


class SystemHealth(BaseModel):
    status: ComponentState
    application: ComponentHealth
    database: ComponentHealth
    assets: ComponentHealth
    ollama: OllamaComponentHealth

    model_config = ConfigDict(frozen=True)
