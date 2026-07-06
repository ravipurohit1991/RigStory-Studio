from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.infrastructure.llm.provider import ModelInfo


class OllamaModelsRead(BaseModel):
    available: bool
    base_url: str
    models: tuple[ModelInfo, ...] = ()
    detail: str | None = None

    model_config = ConfigDict(frozen=True)


class OllamaTestRequest(BaseModel):
    model: str = Field(min_length=1)
    prompt: str = "Reply that the connection works."

    model_config = ConfigDict(frozen=True)


class OllamaTestResult(BaseModel):
    ok: bool
    model: str
    latency_ms: float | None = None
    detail: str
    raw_response: str | None = None

    model_config = ConfigDict(frozen=True)
