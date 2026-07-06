from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.deps import get_health_service
from app.main import app
from app.schemas.health import (
    ComponentHealth,
    ComponentState,
    OllamaComponentHealth,
    SystemHealth,
)


class FakeHealthService:
    async def check(self) -> SystemHealth:
        return SystemHealth(
            status=ComponentState.healthy,
            application=ComponentHealth(status=ComponentState.healthy, detail="app"),
            database=ComponentHealth(status=ComponentState.healthy, detail="db"),
            assets=ComponentHealth(status=ComponentState.healthy, detail="assets"),
            ollama=OllamaComponentHealth(
                status=ComponentState.unavailable,
                base_url="http://localhost:11434",
                detail="connection refused",
            ),
        )


def test_health_distinguishes_core_app_from_ollama(client: TestClient) -> None:
    app.dependency_overrides[get_health_service] = FakeHealthService

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"
    assert payload["database"]["status"] == "healthy"
    assert payload["ollama"]["status"] == "unavailable"
    assert payload["ollama"]["base_url"] == "http://localhost:11434"
