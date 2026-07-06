from __future__ import annotations

import pytest

from app.domain.migrations import (
    JsonDocument,
    MigrationError,
    MigrationRegistry,
    migrate_project_document,
)
from app.domain.versioning import PROJECT_SCHEMA_VERSION, SchemaVersion
from tests.sample_paths import load_sample


def test_legacy_project_fixture_migrates_to_current() -> None:
    raw = load_sample("migrations/empty-project-0.1.0.rigstory.json")
    result = migrate_project_document(raw)
    assert result.applied == (
        "0.1.0->0.2.0",
        "0.2.0->0.3.0",
        "0.3.0->0.4.0",
        "0.4.0->0.5.0",
        "0.5.0->0.6.0",
    )
    assert result.document["schema_version"] == str(PROJECT_SCHEMA_VERSION)
    assert result.document["generation_records"] == []
    assert result.document["motion_plans"] == []


def test_current_version_is_a_no_op() -> None:
    raw = load_sample("projects/empty-project.rigstory.json")
    result = migrate_project_document(raw)
    assert result.applied == ()
    assert result.document == raw


def test_future_version_rejected() -> None:
    raw = load_sample("invalid/project-future-version.rigstory.json")
    with pytest.raises(MigrationError, match="newer than supported"):
        migrate_project_document(raw)


def test_missing_schema_version_rejected() -> None:
    with pytest.raises(MigrationError, match="no schema_version"):
        migrate_project_document({"format": "rigstory-project"})


def test_unknown_version_without_path_rejected() -> None:
    document: JsonDocument = {"schema_version": "0.0.1"}
    with pytest.raises(MigrationError, match="no migration path"):
        migrate_project_document(document)


def test_registry_rejects_duplicate_source() -> None:
    registry = MigrationRegistry("test")
    registry.register("1.0.0", "1.1.0")(lambda document: document)
    with pytest.raises(MigrationError, match="duplicate migration"):
        registry.register("1.0.0", "1.2.0")(lambda document: document)


def test_registry_rejects_non_increasing_step() -> None:
    registry = MigrationRegistry("test")
    with pytest.raises(MigrationError, match="must increase"):
        registry.register("1.1.0", "1.0.0")(lambda document: document)


def test_registry_chains_steps_in_order() -> None:
    registry = MigrationRegistry("test")

    @registry.register("1.0.0", "1.1.0")
    def _first(document: JsonDocument) -> JsonDocument:
        document["first"] = True
        return document

    @registry.register("1.1.0", "2.0.0")
    def _second(document: JsonDocument) -> JsonDocument:
        document["second"] = True
        return document

    result = registry.migrate({"schema_version": "1.0.0"}, SchemaVersion(2, 0, 0))
    assert result.applied == ("1.0.0->1.1.0", "1.1.0->2.0.0")
    assert result.document["first"] is True
    assert result.document["second"] is True
    assert result.document["schema_version"] == "2.0.0"


def test_walker_fixture_migrates_and_derives_scene_flags() -> None:
    raw = load_sample("migrations/walker-project-0.3.0.rigstory.json")
    result = migrate_project_document(raw)
    assert result.from_version == "0.3.0"
    assert result.to_version == str(PROJECT_SCHEMA_VERSION)
    assert result.applied == ("0.3.0->0.4.0", "0.4.0->0.5.0", "0.5.0->0.6.0")
    scenes = result.document["scenes"]
    assert isinstance(scenes, list) and isinstance(scenes[0], dict)
    objects = scenes[0]["objects"]
    assert isinstance(objects, list) and isinstance(objects[0], dict)
    floor = objects[0]
    assert floor["walkable"] is True
    assert floor["visible"] is True
    assert floor["collision_mask"] == ["ground"]
    clips = result.document["clips"]
    assert isinstance(clips, list) and isinstance(clips[0], dict)
    assert clips[0]["source_plan_id"] is None
    assert clips[0]["engine_version"] is None


def test_migration_result_reports_source_and_target_versions() -> None:
    raw = load_sample("migrations/empty-project-0.1.0.rigstory.json")
    result = migrate_project_document(raw)
    assert result.from_version == "0.1.0"
    assert result.to_version == str(PROJECT_SCHEMA_VERSION)

    current = migrate_project_document(load_sample("projects/empty-project.rigstory.json"))
    assert current.from_version == current.to_version == str(PROJECT_SCHEMA_VERSION)


def test_registry_preserves_unknown_fields() -> None:
    registry = MigrationRegistry("test")
    registry.register("1.0.0", "1.1.0")(lambda document: document)
    result = registry.migrate(
        {"schema_version": "1.0.0", "future_field": {"kept": True}},
        SchemaVersion(1, 1, 0),
    )
    assert result.document["future_field"] == {"kept": True}
