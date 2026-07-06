"""HTTP-based Ollama provider (specs §21.2).

Talks to a local Ollama server over its REST API and hides it behind
:class:`LLMProvider`. The Ollama Python package is intentionally not imported,
which keeps this the only module that knows the wire format.
"""

from __future__ import annotations

from time import perf_counter
from typing import Any

import httpx

from app.domain.canonical import JsonValue
from app.infrastructure.llm.provider import (
    ChatMessage,
    ChatResult,
    GenerationOptions,
    ModelInfo,
    ProviderError,
    ProviderHealth,
    ProviderState,
    ProviderTimeoutError,
)


class OllamaProvider:
    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._health_timeout = timeout_seconds
        # An injectable transport lets tests stub the wire without a live server.
        self._transport = transport

    @property
    def base_url(self) -> str:
        return self._base_url

    def _client(self, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout,
            transport=self._transport,
        )

    async def health(self) -> ProviderHealth:
        started = perf_counter()
        try:
            async with self._client(self._health_timeout) as client:
                response = await client.get("/api/version")
            latency_ms = (perf_counter() - started) * 1000
            if response.is_success:
                return ProviderHealth(
                    status=ProviderState.healthy,
                    base_url=self._base_url,
                    detail="Ollama responded to /api/version.",
                    latency_ms=round(latency_ms, 2),
                )
            return ProviderHealth(
                status=ProviderState.unavailable,
                base_url=self._base_url,
                detail=f"Ollama returned HTTP {response.status_code}.",
                latency_ms=round(latency_ms, 2),
            )
        except httpx.TimeoutException:
            return ProviderHealth(
                status=ProviderState.unavailable,
                base_url=self._base_url,
                detail="Ollama health check timed out.",
            )
        except httpx.HTTPError as exc:
            return ProviderHealth(
                status=ProviderState.unavailable,
                base_url=self._base_url,
                detail=str(exc),
            )

    async def list_models(self) -> list[ModelInfo]:
        try:
            async with self._client(self._health_timeout) as client:
                response = await client.get("/api/tags")
                response.raise_for_status()
                payload = response.json()
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("Listing Ollama models timed out.") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"Listing Ollama models failed: {exc}") from exc
        except ValueError as exc:
            raise ProviderError("Ollama returned a non-JSON model list.") from exc
        return [_parse_model(entry) for entry in payload.get("models", [])]

    async def chat(
        self,
        *,
        model: str,
        messages: list[ChatMessage],
        options: GenerationOptions,
        format_schema: dict[str, JsonValue] | None = None,
    ) -> ChatResult:
        request_body: dict[str, Any] = {
            "model": model,
            "messages": [message.model_dump() for message in messages],
            "stream": False,
            "options": {"temperature": options.temperature},
        }
        if options.num_ctx is not None:
            request_body["options"]["num_ctx"] = options.num_ctx
        if options.keep_alive is not None:
            request_body["keep_alive"] = options.keep_alive
        if format_schema is not None:
            request_body["format"] = format_schema

        try:
            async with self._client(options.timeout_seconds) as client:
                response = await client.post("/api/chat", json=request_body)
                response.raise_for_status()
                payload = response.json()
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(
                f"Ollama chat timed out after {options.timeout_seconds}s."
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"Ollama chat failed: {exc}") from exc
        except ValueError as exc:
            raise ProviderError("Ollama returned a non-JSON chat response.") from exc

        message = payload.get("message")
        if not isinstance(message, dict) or "content" not in message:
            raise ProviderError("Ollama chat response did not contain a message.")
        return ChatResult(
            content=str(message["content"]),
            model=str(payload.get("model", model)),
            done_reason=payload.get("done_reason"),
            total_duration_ns=payload.get("total_duration"),
            load_duration_ns=payload.get("load_duration"),
            prompt_eval_count=payload.get("prompt_eval_count"),
            prompt_eval_duration_ns=payload.get("prompt_eval_duration"),
            eval_count=payload.get("eval_count"),
            eval_duration_ns=payload.get("eval_duration"),
        )


def _parse_model(entry: dict[str, Any]) -> ModelInfo:
    details = entry.get("details") or {}
    return ModelInfo(
        name=str(entry.get("name", "")),
        size_bytes=entry.get("size"),
        family=details.get("family"),
        parameter_size=details.get("parameter_size"),
        quantization=details.get("quantization_level"),
        modified_at=entry.get("modified_at"),
    )
