from __future__ import annotations

from typing import cast

import pytest
from pydantic import ValidationError

from app.domain.canonical import JsonValue
from app.domain.errors import DomainValidationError
from app.domain.project import (
    load_project_document,
    parse_project_document,
    validate_project_document,
)
from app.domain.scene import MAX_ACTORS_PER_SCENE
from tests.sample_paths import load_sample


def test_biped_demo_loads_clean() -> None:
    loaded = load_project_document(load_sample("projects/biped-demo.rigstory.json"))
    document = loaded.document
    assert loaded.migration.applied == ()
    assert len(document.characters) == 2
    assert len(document.scenes) == 3
    assert len(document.clips) == 1
    assert len(document.characters[0].rig.bones) == 25
    actor_counts = sorted(len(scene.actors) for scene in document.scenes)
    assert actor_counts == [0, 1, 2]


def test_empty_project_loads_clean() -> None:
    loaded = load_project_document(load_sample("projects/empty-project.rigstory.json"))
    assert loaded.document.characters == ()
    assert loaded.document.scenes == ()


def test_bad_reference_codes() -> None:
    raw = load_sample("invalid/project-bad-refs.rigstory.json")
    document = parse_project_document(raw)
    codes = {issue.code for issue in validate_project_document(document)}
    assert "CLIP_UNKNOWN_BONE" in codes
    assert "CLIP_KEYFRAME_ORDER" in codes


def test_invalid_clip_loop_range_detected() -> None:
    raw = load_sample("projects/biped-demo.rigstory.json")
    clips = cast(list[dict[str, JsonValue]], raw["clips"])
    clips[0]["loop_range"] = [0.8, 0.2]
    document = parse_project_document(raw)
    codes = {issue.code for issue in validate_project_document(document)}
    assert "CLIP_LOOP_RANGE_INVALID" in codes


def test_three_actors_rejected_at_parse_time() -> None:
    assert MAX_ACTORS_PER_SCENE == 2
    raw = load_sample("invalid/project-three-actors.rigstory.json")
    with pytest.raises(ValidationError, match="at most 2"):
        parse_project_document(raw)


def test_inverted_joint_limit_rejected_at_parse_time() -> None:
    raw = load_sample("invalid/project-inverted-joint-limit.rigstory.json")
    with pytest.raises(ValidationError, match="inverted"):
        parse_project_document(raw)


def test_unknown_character_reference_detected() -> None:
    raw = load_sample("projects/biped-demo.rigstory.json")
    # Drop all characters so every actor reference dangles.
    raw["characters"] = []
    document = parse_project_document(raw)
    codes = {issue.code for issue in validate_project_document(document)}
    assert "SCENE_UNKNOWN_CHARACTER" in codes


def test_unknown_clip_scene_detected() -> None:
    raw = load_sample("projects/biped-demo.rigstory.json")
    raw["scenes"] = []
    document = parse_project_document(raw)
    codes = {issue.code for issue in validate_project_document(document)}
    assert "CLIP_UNKNOWN_SCENE" in codes


def test_load_rejects_invalid_documents() -> None:
    raw = load_sample("invalid/project-bad-refs.rigstory.json")
    with pytest.raises(DomainValidationError):
        load_project_document(raw)


def test_wrong_schema_version_flagged_by_invariants() -> None:
    raw = load_sample("projects/empty-project.rigstory.json")
    raw["schema_version"] = "0.1.0"
    document = parse_project_document(raw)
    codes = {issue.code for issue in validate_project_document(document)}
    assert "PROJECT_UNSUPPORTED_VERSION" in codes


def test_generated_character_project_loads_clean() -> None:
    loaded = load_project_document(load_sample("projects/generated-character.rigstory.json"))
    assert loaded.migration.applied == ()
    assert len(loaded.document.characters) == 1
    assert len(loaded.document.generation_records) == 1
    record = loaded.document.generation_records[0]
    assert record.blueprint is not None
    assert record.character_id == loaded.document.characters[0].id


def test_generation_record_unknown_character_detected() -> None:
    raw = load_sample("projects/generated-character.rigstory.json")
    raw["characters"] = []
    document = parse_project_document(raw)
    codes = {issue.code for issue in validate_project_document(document)}
    assert "GENERATION_UNKNOWN_CHARACTER" in codes
