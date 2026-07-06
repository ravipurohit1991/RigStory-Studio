from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_llm_provider
from app.infrastructure.llm.mock import ScriptedLLMProvider, content_result
from app.infrastructure.llm.provider import (
    ChatResult,
    ModelInfo,
    ProviderError,
    ProviderHealth,
    ProviderState,
)
from app.main import app


class _DownProvider:
    async def health(self) -> ProviderHealth:
        return ProviderHealth(status=ProviderState.unavailable, base_url="mock://local")

    async def list_models(self) -> list[ModelInfo]:
        raise ProviderError("connection refused")

    async def chat(self, **_kwargs: object) -> ChatResult:
        raise ProviderError("connection refused")


@pytest.fixture(autouse=True)
def _clear_overrides() -> Generator[None, None, None]:
    yield
    app.dependency_overrides.clear()


def test_list_models_returns_installed_models() -> None:
    provider = ScriptedLLMProvider(models=[ModelInfo(name="qwen2.5:7b", parameter_size="7B")])
    app.dependency_overrides[get_llm_provider] = lambda: provider
    with TestClient(app) as client:
        response = client.get("/api/v1/ollama/models")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["models"][0]["name"] == "qwen2.5:7b"


def test_list_models_degrades_when_ollama_down() -> None:
    app.dependency_overrides[get_llm_provider] = lambda: _DownProvider()
    with TestClient(app) as client:
        response = client.get("/api/v1/ollama/models")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert body["models"] == []


def test_model_test_reports_structured_output_support() -> None:
    provider = ScriptedLLMProvider([content_result('{"ok": true, "message": "connected"}')])
    app.dependency_overrides[get_llm_provider] = lambda: provider
    with TestClient(app) as client:
        response = client.post("/api/v1/ollama/test", json={"model": "qwen2.5:7b"})
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    # A structured-output schema was sent for the smoke test.
    assert provider.formats[0] is not None


def test_model_test_flags_non_schema_response() -> None:
    provider = ScriptedLLMProvider([content_result("I cannot do JSON")])
    app.dependency_overrides[get_llm_provider] = lambda: provider
    with TestClient(app) as client:
        response = client.post("/api/v1/ollama/test", json={"model": "qwen2.5:7b"})
    assert response.status_code == 200
    assert response.json()["ok"] is False


def test_model_test_reports_provider_error() -> None:
    app.dependency_overrides[get_llm_provider] = lambda: _DownProvider()
    with TestClient(app) as client:
        response = client.post("/api/v1/ollama/test", json={"model": "qwen2.5:7b"})
    assert response.status_code == 200
    assert response.json()["ok"] is False
