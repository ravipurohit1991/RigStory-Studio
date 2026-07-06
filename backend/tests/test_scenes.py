from __future__ import annotations

from fastapi.testclient import TestClient

from tests.domain.test_scene_phase6 import room_scene
from tests.sample_paths import load_sample


def test_scene_crud_snapshot_and_validation_routes(client: TestClient) -> None:
    created = client.post(
        "/api/v1/projects", json={"document": load_sample("projects/biped-demo.rigstory.json")}
    )
    assert created.status_code == 201
    project_id = created.json()["document"]["project"]["id"]
    revision = created.json()["revision"]

    scene = room_scene().model_copy(update={"id": "scene_demo_room"}).model_dump(mode="json")
    added = client.post(
        f"/api/v1/projects/{project_id}/scenes",
        json={"scene": scene, "expected_revision": revision},
    )
    assert added.status_code == 201
    next_revision = added.json()["revision"]

    listed = client.get(f"/api/v1/projects/{project_id}/scenes")
    assert listed.status_code == 200
    assert "scene_demo_room" in {item["id"] for item in listed.json()}

    snapshot = client.get("/api/v1/scenes/scene_demo_room/snapshot")
    assert snapshot.status_code == 200
    body = snapshot.json()
    assert body["byte_length"] < 5000
    assert "texture" not in body["canonical_json"].lower()
    assert body["snapshot"]["walkable_regions"] == ["floor_main"]

    validation = client.post("/api/v1/scenes/scene_demo_room/validate")
    assert validation.status_code == 200
    assert validation.json()["issues"] == []

    stale = client.patch(
        "/api/v1/scenes/scene_demo_room",
        json={"scene": scene, "expected_revision": revision},
    )
    assert stale.status_code == 409

    deleted = client.delete(
        "/api/v1/scenes/scene_demo_room", params={"expected_revision": next_revision}
    )
    assert deleted.status_code == 200
