from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.deps import (
    get_character_generation_service,
    get_job_runner,
)
from app.application.characters.generate import CharacterGenerationService
from app.application.jobs import InlineJobRunner
from app.domain.blueprint import CANNED_BLUEPRINT
from app.infrastructure.llm.mock import ScriptedLLMProvider, content_result, model_result
from app.infrastructure.llm.prompt_registry import PromptRegistry
from app.main import app
from app.schemas.characters import MAX_PROMPT_TEXT_LENGTH
from app.services.project_store import FileProjectStore


def _install_generation(
    tmp_path: Path, provider: ScriptedLLMProvider
) -> Callable[[], CharacterGenerationService]:
    store = FileProjectStore(tmp_path)
    runner = InlineJobRunner()

    def make_service() -> CharacterGenerationService:
        return CharacterGenerationService(
            provider=provider, prompt_registry=PromptRegistry(), store=store
        )

    app.dependency_overrides[get_job_runner] = lambda: runner
    app.dependency_overrides[get_character_generation_service] = make_service
    return make_service


def _create_project(client: TestClient) -> tuple[str, str]:
    created = client.post("/api/v1/projects", json={"name": "AI Studio"}).json()
    return created["document"]["project"]["id"], created["revision"]


def test_generate_character_end_to_end(client: TestClient, tmp_path: Path) -> None:
    project_id, revision = _create_project(client)
    _install_generation(tmp_path, ScriptedLLMProvider([model_result(CANNED_BLUEPRINT)]))

    response = client.post(
        f"/api/v1/projects/{project_id}/characters/generate",
        json={"model": "planner", "description": "a calm woman", "expected_revision": revision},
    )
    assert response.status_code == 202
    job = response.json()
    assert job["state"] == "succeeded"
    result = job["result"]
    assert result["status"] == "succeeded"
    assert result["character_id"].startswith("char_")
    assert any(entry["source"] == "model" for entry in result["provenance"])
    assert result["blueprint"]["character_name"]

    # The job is retrievable and the character/record were committed.
    fetched = client.get(f"/api/v1/jobs/{job['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["state"] == "succeeded"

    characters = client.get(f"/api/v1/projects/{project_id}/characters").json()
    assert len(characters) == 1
    assert len(characters[0]["rig"]["bones"]) == 25

    project = client.get(f"/api/v1/projects/{project_id}").json()
    records = project["document"]["generation_records"]
    assert len(records) == 1
    assert records[0]["model_name"]
    assert records[0]["blueprint"]["character_name"]


def test_generate_repairs_invalid_first_response(client: TestClient, tmp_path: Path) -> None:
    project_id, revision = _create_project(client)
    _install_generation(
        tmp_path,
        ScriptedLLMProvider([content_result("not json at all"), model_result(CANNED_BLUEPRINT)]),
    )

    response = client.post(
        f"/api/v1/projects/{project_id}/characters/generate",
        json={"model": "planner", "description": "x", "expected_revision": revision},
    )
    assert response.status_code == 202
    assert response.json()["result"]["status"] == "repaired"


def test_generate_failure_leaves_project_unchanged(client: TestClient, tmp_path: Path) -> None:
    project_id, revision = _create_project(client)
    _install_generation(
        tmp_path, ScriptedLLMProvider([content_result("bad one"), content_result("bad two")])
    )

    response = client.post(
        f"/api/v1/projects/{project_id}/characters/generate",
        json={"model": "planner", "description": "x", "expected_revision": revision},
    )
    assert response.status_code == 202
    job = response.json()
    assert job["state"] == "failed"
    assert job["error_kind"] == "invalid_response"
    assert job["retryable"] is False

    # No character was added and the revision is unchanged.
    characters = client.get(f"/api/v1/projects/{project_id}/characters").json()
    assert characters == []
    current = client.get(f"/api/v1/projects/{project_id}").json()
    assert current["revision"] == revision


def test_generate_timeout_is_retryable(client: TestClient, tmp_path: Path) -> None:
    from app.infrastructure.llm.provider import ProviderTimeoutError

    project_id, revision = _create_project(client)
    _install_generation(tmp_path, ScriptedLLMProvider([ProviderTimeoutError("slow")]))

    response = client.post(
        f"/api/v1/projects/{project_id}/characters/generate",
        json={"model": "planner", "description": "x", "expected_revision": revision},
    )
    job = response.json()
    assert job["state"] == "failed"
    assert job["error_kind"] == "timeout"
    assert job["retryable"] is True


def test_generate_rejects_oversized_prompt_before_job_starts(
    client: TestClient, tmp_path: Path
) -> None:
    project_id, revision = _create_project(client)
    provider = ScriptedLLMProvider([model_result(CANNED_BLUEPRINT)])
    _install_generation(tmp_path, provider)

    response = client.post(
        f"/api/v1/projects/{project_id}/characters/generate",
        json={
            "model": "planner",
            "description": "x" * (MAX_PROMPT_TEXT_LENGTH + 1),
            "expected_revision": revision,
        },
    )

    assert response.status_code == 422
    assert provider.calls == []


def test_job_events_stream_reports_terminal_state(client: TestClient, tmp_path: Path) -> None:
    project_id, revision = _create_project(client)
    _install_generation(tmp_path, ScriptedLLMProvider([model_result(CANNED_BLUEPRINT)]))

    job = client.post(
        f"/api/v1/projects/{project_id}/characters/generate",
        json={"model": "planner", "description": "x", "expected_revision": revision},
    ).json()

    events = client.get(f"/api/v1/jobs/{job['id']}/events")
    assert events.status_code == 200
    assert "event: state" in events.text


def test_unknown_job_returns_404(client: TestClient) -> None:
    assert client.get("/api/v1/jobs/job_missing").status_code == 404
