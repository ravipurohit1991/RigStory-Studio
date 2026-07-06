from __future__ import annotations

from typing import cast

from fastapi.testclient import TestClient

from tests.sample_paths import load_sample


def test_character_crud_is_project_revisioned(client: TestClient) -> None:
    raw = load_sample("projects/biped-demo.rigstory.json")
    created = client.post("/api/v1/projects", json={"document": raw}).json()
    project_id = created["document"]["project"]["id"]
    revision = created["revision"]

    list_response = client.get(f"/api/v1/projects/{project_id}/characters")
    assert list_response.status_code == 200
    assert [character["id"] for character in list_response.json()] == [
        "char_biped_alpha",
        "char_biped_beta",
    ]

    character = created["document"]["characters"][0]
    character["name"] = "Mira Renamed"
    updated = client.patch(
        "/api/v1/characters/char_biped_alpha",
        json={"character": character, "expected_revision": revision},
    )
    assert updated.status_code == 200
    assert updated.json()["document"]["characters"][0]["name"] == "Mira Renamed"
    next_revision = updated.json()["revision"]
    assert next_revision != revision

    fetched = client.get("/api/v1/characters/char_biped_alpha")
    assert fetched.status_code == 200
    assert fetched.json()["character"]["name"] == "Mira Renamed"
    assert fetched.json()["revision"] == next_revision

    stale = client.patch(
        "/api/v1/characters/char_biped_alpha",
        json={"character": character, "expected_revision": revision},
    )
    assert stale.status_code == 409


def test_character_delete_preserves_reference_integrity(client: TestClient) -> None:
    raw = load_sample("projects/biped-demo.rigstory.json")
    created = client.post("/api/v1/projects", json={"document": raw}).json()

    response = client.delete(
        "/api/v1/characters/char_biped_alpha",
        params={"expected_revision": created["revision"]},
    )

    assert response.status_code == 422
    assert "SCENE_UNKNOWN_CHARACTER" in {issue["code"] for issue in response.json()["detail"]}


def test_character_create_and_delete_without_scene_references(client: TestClient) -> None:
    created = client.post("/api/v1/projects", json={"name": "Character Library"}).json()
    project_id = created["document"]["project"]["id"]
    sample_characters = cast(
        list[dict[str, object]],
        load_sample("projects/biped-demo.rigstory.json")["characters"],
    )
    character = sample_characters[0]

    added = client.post(
        f"/api/v1/projects/{project_id}/characters",
        json={"character": character, "expected_revision": created["revision"]},
    )
    assert added.status_code == 201
    assert added.json()["document"]["characters"][0]["id"] == "char_biped_alpha"

    deleted = client.delete(
        "/api/v1/characters/char_biped_alpha",
        params={"expected_revision": added.json()["revision"]},
    )
    assert deleted.status_code == 200
    assert deleted.json()["document"]["characters"] == []


def test_character_builder_preview_does_not_require_ollama(client: TestClient) -> None:
    presets = client.get("/api/v1/characters/builder-presets")
    assert presets.status_code == 200
    assert len(presets.json()) >= 10

    response = client.post(
        "/api/v1/characters/build",
        json={
            "name": "Preview Human",
            "presentation": "neutral",
            "age_category": "adult",
            "height": "average",
            "build": "average",
            "hair_style": "short",
            "face_shape": "oval",
            "top": "tshirt",
            "bottom": "trousers",
            "footwear": "shoes",
            "outerwear": "none",
            "style": "flat_vector",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["character"]["id"].startswith("char_proc_")
    assert body["character"]["rig"]["id"].startswith("rig_proc_")
    assert body["character"]["attachments"]
    assert {constraint["id"] for constraint in body["constraints"]} >= {"ik_arm_l", "look_head"}
    assert not any(diagnostic["severity"] == "error" for diagnostic in body["diagnostics"])
