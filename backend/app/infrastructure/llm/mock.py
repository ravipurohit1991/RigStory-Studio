"""In-process LLM providers for tests and model-independent operation.

``ScriptedLLMProvider`` returns a fixed queue of responses (or raises queued
errors), which lets the repair loop, job runner, and API be exercised without a
live model (plan.md §10).
"""

from __future__ import annotations

from collections import deque

from pydantic import BaseModel

from app.domain.canonical import JsonValue, canonical_json_dumps
from app.infrastructure.llm.provider import (
    ChatMessage,
    ChatResult,
    GenerationOptions,
    ModelInfo,
    ProviderError,
    ProviderHealth,
    ProviderState,
)

DEFAULT_MOCK_MODEL = "mock-model"


def content_result(content: str, *, model: str = DEFAULT_MOCK_MODEL) -> ChatResult:
    return ChatResult(
        content=content,
        model=model,
        done_reason="stop",
        total_duration_ns=1_000_000,
        load_duration_ns=100_000,
        prompt_eval_count=32,
        prompt_eval_duration_ns=400_000,
        eval_count=64,
        eval_duration_ns=500_000,
    )


def model_result(model_obj: BaseModel, *, model: str = DEFAULT_MOCK_MODEL) -> ChatResult:
    return content_result(canonical_json_dumps(model_obj.model_dump(mode="json")), model=model)


class ScriptedLLMProvider:
    """A provider that replays queued chat results or raises queued errors."""

    def __init__(
        self,
        responses: list[ChatResult | Exception] | None = None,
        *,
        models: list[ModelInfo] | None = None,
        healthy: bool = True,
    ) -> None:
        self._responses: deque[ChatResult | Exception] = deque(responses or [])
        self._models = models if models is not None else [ModelInfo(name=DEFAULT_MOCK_MODEL)]
        self._healthy = healthy
        self.calls: list[list[ChatMessage]] = []
        self.formats: list[dict[str, JsonValue] | None] = []

    def queue(self, response: ChatResult | Exception) -> None:
        self._responses.append(response)

    async def health(self) -> ProviderHealth:
        status = ProviderState.healthy if self._healthy else ProviderState.unavailable
        return ProviderHealth(status=status, base_url="mock://local", latency_ms=0.0)

    async def list_models(self) -> list[ModelInfo]:
        return list(self._models)

    async def chat(
        self,
        *,
        model: str,
        messages: list[ChatMessage],
        options: GenerationOptions,
        format_schema: dict[str, JsonValue] | None = None,
    ) -> ChatResult:
        self.calls.append(messages)
        self.formats.append(format_schema)
        if not self._responses:
            raise ProviderError("ScriptedLLMProvider ran out of queued responses.")
        response = self._responses.popleft()
        if isinstance(response, Exception):
            raise response
        return response
