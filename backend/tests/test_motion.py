from __future__ import annotations

from fastapi.testclient import TestClient

from tests.domain.test_scene_phase6 import room_scene
from tests.sample_paths import load_sample


def test_demo_motion_compile_route(client: TestClient) -> None:
    created = client.post(
        "/api/v1/projects", json={"document": load_sample("projects/biped-demo.rigstory.json")}
    )
    project_id = created.json()["document"]["project"]["id"]
    added = client.post(
        f"/api/v1/projects/{project_id}/scenes",
        json={
            "scene": room_scene()
            .model_copy(update={"id": "scene_phase7_room"})
            .model_dump(mode="json"),
            "expected_revision": created.json()["revision"],
        },
    )
    assert added.status_code == 201

    response = client.post(
        "/api/v1/motion/demo/compile",
        json={
            "scene_id": "scene_phase7_room",
            "actor_id": "actor_mira",
            "character_id": "char_biped_alpha",
            "clip_id": "clip_demo_motion",
            "actions": [
                {"id": "walk", "type": "locomote", "target": [2.2, 0.0], "duration": 2.0},
                {"id": "sit", "type": "sit", "anchor_ref": "chair_main.seat", "duration": 1.0},
                {"id": "wave", "type": "wave", "duration": 1.0, "repetitions": 2},
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["clip"]["id"] == "clip_demo_motion"
    assert body["report"]["metrics"]["max_joint_limit_violation_deg"] == 0.0
