from __future__ import annotations

import re

import pytest

from app.domain import ids
from app.domain.versioning import SchemaVersion

FACTORIES_AND_PATTERNS = [
    (ids.new_project_id, ids.PROJECT_ID_PATTERN),
    (ids.new_character_id, ids.CHARACTER_ID_PATTERN),
    (ids.new_rig_id, ids.RIG_ID_PATTERN),
    (ids.new_scene_id, ids.SCENE_ID_PATTERN),
    (ids.new_actor_id, ids.ACTOR_ID_PATTERN),
    (ids.new_plan_id, ids.PLAN_ID_PATTERN),
    (ids.new_clip_id, ids.CLIP_ID_PATTERN),
    (ids.new_track_id, ids.TRACK_ID_PATTERN),
    (ids.new_keyframe_id, ids.KEYFRAME_ID_PATTERN),
    (ids.new_asset_id, ids.ASSET_ID_PATTERN),
    (ids.new_job_id, ids.JOB_ID_PATTERN),
    (ids.new_revision_id, ids.REVISION_ID_PATTERN),
]


def test_factories_match_their_patterns() -> None:
    for factory, pattern in FACTORIES_AND_PATTERNS:
        value = factory()
        assert re.fullmatch(pattern, value), f"{value} does not match {pattern}"


def test_factories_produce_unique_values() -> None:
    values = {ids.new_project_id() for _ in range(50)}
    assert len(values) == 50


def test_slug_checks() -> None:
    assert ids.is_slug("chair_1")
    assert not ids.is_slug("Chair")
    assert not ids.is_slug("1chair")
    assert ids.is_namespaced_slug("hair.strand_01")
    assert not ids.is_namespaced_slug("hair..strand")


def test_split_anchor_ref() -> None:
    assert ids.split_anchor_ref("chair_1.seat") == ("chair_1", "seat")
    with pytest.raises(ValueError, match="invalid anchor reference"):
        ids.split_anchor_ref("chair_1")


def test_schema_version_parse_and_compare() -> None:
    assert SchemaVersion.parse("1.2.3") == SchemaVersion(1, 2, 3)
    assert SchemaVersion.parse("0.2.0") > SchemaVersion.parse("0.1.9")
    assert str(SchemaVersion(0, 2, 0)) == "0.2.0"
    with pytest.raises(ValueError, match="invalid semantic version"):
        SchemaVersion.parse("1.2")
