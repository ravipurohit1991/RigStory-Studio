from __future__ import annotations

import json
from time import perf_counter
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from app.api.deps import get_app_settings, get_llm_provider
from app.core.config import Settings
from app.domain.canonical import JsonValue
from app.infrastructure.llm.provider import (
    ChatMessage,
    GenerationOptions,
    LLMProvider,
    ProviderError,
    ProviderTimeoutError,
)
from app.schemas.ollama import OllamaModelsRead, OllamaTestRequest, OllamaTestResult

router = APIRouter(tags=["ollama"])
ProviderDep = Annotated[LLMProvider, Depends(get_llm_provider)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]


class _SmokeSchema(BaseModel):
    """Tiny schema used to probe structured-output support (specs §23.1)."""

    ok: bool
    message: str

    model_config = ConfigDict(frozen=True)


@router.get("/ollama/models", response_model=OllamaModelsRead)
async def list_ollama_models(provider: ProviderDep, settings: SettingsDep) -> OllamaModelsRead:
    try:
        models = await provider.list_models()
    except ProviderTimeoutError:
        return OllamaModelsRead(
            available=False,
            base_url=settings.ollama_base_url,
            detail="Ollama did not respond in time.",
        )
    except ProviderError as exc:
        return OllamaModelsRead(
            available=False,
            base_url=settings.ollama_base_url,
            detail=str(exc),
        )
    return OllamaModelsRead(
        available=True,
        base_url=settings.ollama_base_url,
        models=tuple(models),
        detail=f"{len(models)} model(s) installed.",
    )


@router.post("/ollama/test", response_model=OllamaTestResult)
async def test_ollama_model(
    payload: OllamaTestRequest,
    provider: ProviderDep,
    settings: SettingsDep,
) -> OllamaTestResult:
    schema: dict[str, JsonValue] = _SmokeSchema.model_json_schema()
    messages = [
        ChatMessage(
            role="system",
            content="Return only a JSON object matching the schema. Set ok to true.",
        ),
        ChatMessage(role="user", content=payload.prompt),
    ]
    options = GenerationOptions(
        temperature=0.0,
        keep_alive=settings.ollama_keep_alive,
        timeout_seconds=min(settings.ollama_generation_timeout_seconds, 60.0),
    )
    started = perf_counter()
    try:
        result = await provider.chat(
            model=payload.model,
            messages=messages,
            options=options,
            format_schema=schema,
        )
    except ProviderTimeoutError:
        return OllamaTestResult(
            ok=False, model=payload.model, detail="The model did not respond in time."
        )
    except ProviderError as exc:
        return OllamaTestResult(ok=False, model=payload.model, detail=str(exc))

    latency_ms = round((perf_counter() - started) * 1000, 2)
    try:
        parsed = _SmokeSchema.model_validate(json.loads(result.content))
    except (json.JSONDecodeError, ValueError):
        return OllamaTestResult(
            ok=False,
            model=payload.model,
            latency_ms=latency_ms,
            detail="The model responded but did not honor the structured-output schema.",
            raw_response=result.content,
        )
    return OllamaTestResult(
        ok=parsed.ok,
        model=result.model or payload.model,
        latency_ms=latency_ms,
        detail="Structured-output smoke test succeeded.",
        raw_response=result.content,
    )
