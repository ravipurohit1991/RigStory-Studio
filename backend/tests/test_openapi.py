from __future__ import annotations

from fastapi.testclient import TestClient


def test_openapi_schema_is_reachable(client: TestClient) -> None:
    response = client.get("/api/v1/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/health" in paths
    assert "/api/v1/projects" in paths
