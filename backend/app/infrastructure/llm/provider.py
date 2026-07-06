"""Provider-neutral LLM interface (specs §21.1, AGENTS §2).

The rest of the application depends only on this module, never on Ollama or
``httpx`` directly, so the provider stays testable and replaceable. The provider
is a thin transport: it performs one chat round trip and returns the raw model
content plus timing metadata. Schema validation and the repair loop live in the
application layer so raw and validated records can be captured separately.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.domain.canonical import JsonValue


class ProviderState(StrEnum):
    healthy = "healthy"
    unavailable = "unavailable"
    error = "error"


class ProviderHealth(BaseModel):
    status: ProviderState
    base_url: str
    detail: str | None = None
    latency_ms: float | None = None

    model_config = ConfigDict(frozen=True)


class ModelInfo(BaseModel):
    name: str
    size_bytes: int | None = None
    family: str | None = None
    parameter_size: str | None = None
    quantization: str | None = None
    modified_at: str | None = None

    model_config = ConfigDict(frozen=True)


type ChatRole = Literal["system", "user", "assistant"]


class ChatMessage(BaseModel):
    role: ChatRole
    content: str

    model_config = ConfigDict(frozen=True)


class GenerationOptions(BaseModel):
    """Request-time knobs for a single structured generation."""

    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    keep_alive: str | None = "10m"
    timeout_seconds: float = Field(default=60.0, gt=0.0)
    num_ctx: int | None = Field(default=None, ge=0)

    model_config = ConfigDict(frozen=True)


class ChatResult(BaseModel):
    """Raw result of one chat call. Durations are nanoseconds, as Ollama reports."""

    content: str
    model: str
    done_reason: str | None = None
    total_duration_ns: int | None = None
    load_duration_ns: int | None = None
    prompt_eval_count: int | None = None
    prompt_eval_duration_ns: int | None = None
    eval_count: int | None = None
    eval_duration_ns: int | None = None

    model_config = ConfigDict(frozen=True)


class ProviderError(Exception):
    """The provider could not complete the request (transport or HTTP error)."""


class ProviderTimeoutError(ProviderError):
    """The provider did not respond within the configured timeout."""


class LLMProvider(Protocol):
    async def health(self) -> ProviderHealth:
        """Return provider reachability without requesting generation."""
        ...

    async def list_models(self) -> list[ModelInfo]:
        """List models installed on the local provider."""
        ...

    async def chat(
        self,
        *,
        model: str,
        messages: list[ChatMessage],
        options: GenerationOptions,
        format_schema: dict[str, JsonValue] | None = None,
    ) -> ChatResult:
        """Perform one non-streaming chat completion.

        When ``format_schema`` is provided it is sent as the structured-output
        JSON schema. The returned content is unvalidated model text.
        """
        ...
