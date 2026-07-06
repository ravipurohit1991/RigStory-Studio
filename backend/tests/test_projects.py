from __future__ import annotations

from fastapi.testclient import TestClient

from tests.sample_paths import load_sample


def test_projects_baseline_is_empty(client: TestClient) -> None:
    response = client.get("/api/v1/projects")

    assert response.status_code == 200
    assert response.json() == []


def test_create_save_reload_duplicate_and_delete_project(client: TestClient) -> None:
    create_response = client.post("/api/v1/projects", json={"name": "Manual Cutout"})

    assert create_response.status_code == 201
    created = create_response.json()
    project_id = created["document"]["project"]["id"]
    first_revision = created["revision"]
    assert created["document"]["project"]["name"] == "Manual Cutout"

    list_response = client.get("/api/v1/projects")
    assert list_response.status_code == 200
    assert list_response.json() == [
        {"id": project_id, "name": "Manual Cutout", "revision": first_revision}
    ]

    document = created["document"]
    document["project"]["name"] = "Manual Cutout Saved"
    update_response = client.patch(
        f"/api/v1/projects/{project_id}",
        json={"document": document, "expected_revision": first_revision},
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["revision"] != first_revision

    reload_response = client.get(f"/api/v1/projects/{project_id}")
    assert reload_response.status_code == 200
    assert reload_response.json()["document"]["project"]["name"] == "Manual Cutout Saved"

    duplicate_response = client.post(f"/api/v1/projects/{project_id}/duplicate")
    assert duplicate_response.status_code == 201
    duplicate = duplicate_response.json()
    assert duplicate["document"]["project"]["id"] != project_id
    assert duplicate["document"]["project"]["name"] == "Manual Cutout Saved Copy"

    delete_response = client.delete(f"/api/v1/projects/{project_id}")
    assert delete_response.status_code == 204
    assert client.get(f"/api/v1/projects/{project_id}").status_code == 404


def test_stale_revision_is_rejected(client: TestClient) -> None:
    created = client.post("/api/v1/projects", json={"name": "Concurrency"}).json()
    project_id = created["document"]["project"]["id"]
    document = created["document"]

    first_update = client.patch(
        f"/api/v1/projects/{project_id}",
        json={"document": document, "expected_revision": created["revision"]},
    )
    assert first_update.status_code == 200

    stale_update = client.patch(
        f"/api/v1/projects/{project_id}",
        json={"document": document, "expected_revision": created["revision"]},
    )
    assert stale_update.status_code == 409


def test_failed_save_preserves_last_good_revision_and_can_restore(client: TestClient) -> None:
    raw = load_sample("projects/biped-demo.rigstory.json")
    created = client.post("/api/v1/projects", json={"document": raw}).json()
    project_id = created["document"]["project"]["id"]
    first_revision = created["revision"]

    valid_document = created["document"]
    valid_document["project"]["name"] = "Good revision"
    second = client.patch(
        f"/api/v1/projects/{project_id}",
        json={"document": valid_document, "expected_revision": first_revision},
    ).json()

    invalid_document = second["document"]
    invalid_document["characters"] = []
    failed = client.patch(
        f"/api/v1/projects/{project_id}",
        json={"document": invalid_document, "expected_revision": second["revision"]},
    )
    assert failed.status_code == 422

    current = client.get(f"/api/v1/projects/{project_id}").json()
    assert current["document"]["project"]["name"] == "Good revision"
    assert current["revision"] == second["revision"]

    revisions = client.get(f"/api/v1/projects/{project_id}/revisions").json()
    assert [revision["sequence"] for revision in revisions] == [1, 2]

    restored = client.post(f"/api/v1/projects/{project_id}/restore/{first_revision}")
    assert restored.status_code == 200
    assert restored.json()["document"]["project"]["name"] == "Biped Demo"
