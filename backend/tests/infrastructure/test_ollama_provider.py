from __future__ import annotations

import json

import httpx
import pytest

from app.domain.canonical import JsonValue
from app.infrastructure.llm.ollama import OllamaProvider
from app.infrastructure.llm.provider import (
    ChatMessage,
    GenerationOptions,
    ProviderError,
    ProviderState,
    ProviderTimeoutError,
)


def _provider(handler: httpx.MockTransport) -> OllamaProvider:
    return OllamaProvider(base_url="http://ollama.test", timeout_seconds=5.0, transport=handler)


async def test_health_reports_healthy_on_version() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/version"
        return httpx.Response(200, json={"version": "0.1.0"})

    provider = _provider(httpx.MockTransport(handler))
    health = await provider.health()
    assert health.status == ProviderState.healthy


async def test_list_models_parses_tags() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(
            200,
            json={
                "models": [
                    {
                        "name": "qwen2.5:7b",
                        "size": 4700000000,
                        "modified_at": "2026-01-01T00:00:00Z",
                        "details": {
                            "family": "qwen2",
                            "parameter_size": "7B",
                            "quantization_level": "Q4_K_M",
                        },
                    }
                ]
            },
        )

    provider = _provider(httpx.MockTransport(handler))
    models = await provider.list_models()
    assert len(models) == 1
    assert models[0].name == "qwen2.5:7b"
    assert models[0].parameter_size == "7B"
    assert models[0].family == "qwen2"


async def test_chat_sends_format_schema_and_returns_content() -> None:
    captured: dict[str, JsonValue] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "model": "qwen2.5:7b",
                "message": {"role": "assistant", "content": '{"ok": true}'},
                "done_reason": "stop",
                "total_duration": 2_000_000,
                "prompt_eval_count": 10,
                "eval_count": 20,
            },
        )

    provider = _provider(httpx.MockTransport(handler))
    result = await provider.chat(
        model="qwen2.5:7b",
        messages=[ChatMessage(role="user", content="hi")],
        options=GenerationOptions(temperature=0.0, num_ctx=4096),
        format_schema={"type": "object"},
    )
    assert result.content == '{"ok": true}'
    assert result.prompt_eval_count == 10
    assert captured["stream"] is False
    assert captured["format"] == {"type": "object"}
    assert captured["options"] == {"temperature": 0.0, "num_ctx": 4096}


async def test_chat_maps_timeout_to_provider_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("boom", request=request)

    provider = _provider(httpx.MockTransport(handler))
    with pytest.raises(ProviderTimeoutError):
        await provider.chat(
            model="m",
            messages=[ChatMessage(role="user", content="hi")],
            options=GenerationOptions(timeout_seconds=0.5),
        )


async def test_chat_maps_http_error_to_provider_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "model not found"})

    provider = _provider(httpx.MockTransport(handler))
    with pytest.raises(ProviderError):
        await provider.chat(
            model="m",
            messages=[ChatMessage(role="user", content="hi")],
            options=GenerationOptions(),
        )


async def test_chat_rejects_response_without_message() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"model": "m"})

    provider = _provider(httpx.MockTransport(handler))
    with pytest.raises(ProviderError):
        await provider.chat(
            model="m",
            messages=[ChatMessage(role="user", content="hi")],
            options=GenerationOptions(),
        )
