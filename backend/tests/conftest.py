from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_project_store
from app.main import app
from app.services.project_store import FileProjectStore


@pytest.fixture
def client(tmp_path: Path) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_project_store] = lambda: FileProjectStore(tmp_path)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
