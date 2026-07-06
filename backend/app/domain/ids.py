"""Typed identifiers for every stable domain object.

Two identifier families exist:

- Prefixed entity IDs (``project_…``, ``char_…``): globally unique values
  minted by the application, never by a model or a user.
- Semantic slug IDs (``hips``, ``forearm_l``, ``chair_1.seat``): stable
  human-readable names that are unique within their owning container.

Stable IDs are never reused for a different object.
"""

from __future__ import annotations

import re
import uuid
from typing import Annotated

from pydantic import StringConstraints

SLUG_PATTERN = r"^[a-z][a-z0-9_]*$"
NAMESPACED_SLUG_PATTERN = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$"
SEMVER_PATTERN = r"^\d+\.\d+\.\d+$"


def _prefixed_pattern(prefix: str) -> str:
    return rf"^{prefix}_[a-z0-9][a-z0-9_-]*$"


PROJECT_ID_PATTERN = _prefixed_pattern("project")
CHARACTER_ID_PATTERN = _prefixed_pattern("char")
RIG_ID_PATTERN = _prefixed_pattern("rig")
SCENE_ID_PATTERN = _prefixed_pattern("scene")
ACTOR_ID_PATTERN = _prefixed_pattern("actor")
PLAN_ID_PATTERN = _prefixed_pattern("plan")
CLIP_ID_PATTERN = _prefixed_pattern("clip")
TRACK_ID_PATTERN = _prefixed_pattern("track")
KEYFRAME_ID_PATTERN = _prefixed_pattern("key")
ASSET_ID_PATTERN = _prefixed_pattern("asset")
JOB_ID_PATTERN = _prefixed_pattern("job")
REVISION_ID_PATTERN = _prefixed_pattern("rev")
GENERATION_RECORD_ID_PATTERN = _prefixed_pattern("gen")

# Prefixed entity identifiers.
ProjectId = Annotated[str, StringConstraints(pattern=PROJECT_ID_PATTERN)]
CharacterId = Annotated[str, StringConstraints(pattern=CHARACTER_ID_PATTERN)]
RigId = Annotated[str, StringConstraints(pattern=RIG_ID_PATTERN)]
SceneId = Annotated[str, StringConstraints(pattern=SCENE_ID_PATTERN)]
ActorId = Annotated[str, StringConstraints(pattern=ACTOR_ID_PATTERN)]
PlanId = Annotated[str, StringConstraints(pattern=PLAN_ID_PATTERN)]
ClipId = Annotated[str, StringConstraints(pattern=CLIP_ID_PATTERN)]
TrackId = Annotated[str, StringConstraints(pattern=TRACK_ID_PATTERN)]
KeyframeId = Annotated[str, StringConstraints(pattern=KEYFRAME_ID_PATTERN)]
AssetId = Annotated[str, StringConstraints(pattern=ASSET_ID_PATTERN)]
JobId = Annotated[str, StringConstraints(pattern=JOB_ID_PATTERN)]
RevisionId = Annotated[str, StringConstraints(pattern=REVISION_ID_PATTERN)]
GenerationRecordId = Annotated[str, StringConstraints(pattern=GENERATION_RECORD_ID_PATTERN)]

# Semantic slug identifiers, unique within their container.
BoneId = Annotated[str, StringConstraints(pattern=NAMESPACED_SLUG_PATTERN)]
AttachmentId = Annotated[str, StringConstraints(pattern=NAMESPACED_SLUG_PATTERN)]
ObjectId = Annotated[str, StringConstraints(pattern=SLUG_PATTERN)]
AnchorId = Annotated[str, StringConstraints(pattern=SLUG_PATTERN)]
ActionId = Annotated[str, StringConstraints(pattern=SLUG_PATTERN)]

# An anchor reference qualifies the anchor with its owning object: "chair_1.seat".
ANCHOR_REF_PATTERN = r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$"
AnchorRef = Annotated[str, StringConstraints(pattern=ANCHOR_REF_PATTERN)]

SchemaVersionStr = Annotated[str, StringConstraints(pattern=SEMVER_PATTERN)]

_SLUG_RE = re.compile(SLUG_PATTERN)
_NAMESPACED_SLUG_RE = re.compile(NAMESPACED_SLUG_PATTERN)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def new_project_id() -> str:
    return _new_id("project")


def new_character_id() -> str:
    return _new_id("char")


def new_rig_id() -> str:
    return _new_id("rig")


def new_scene_id() -> str:
    return _new_id("scene")


def new_actor_id() -> str:
    return _new_id("actor")


def new_plan_id() -> str:
    return _new_id("plan")


def new_clip_id() -> str:
    return _new_id("clip")


def new_track_id() -> str:
    return _new_id("track")


def new_keyframe_id() -> str:
    return _new_id("key")


def new_asset_id() -> str:
    return _new_id("asset")


def new_job_id() -> str:
    return _new_id("job")


def new_revision_id() -> str:
    return _new_id("rev")


def new_generation_record_id() -> str:
    return _new_id("gen")


def is_slug(value: str) -> bool:
    return _SLUG_RE.fullmatch(value) is not None


def is_namespaced_slug(value: str) -> bool:
    return _NAMESPACED_SLUG_RE.fullmatch(value) is not None


def split_anchor_ref(value: str) -> tuple[str, str]:
    """Split ``"chair_1.seat"`` into ``("chair_1", "seat")``."""
    object_id, _, anchor_id = value.partition(".")
    if not object_id or not anchor_id:
        raise ValueError(f"invalid anchor reference: {value!r}")
    return object_id, anchor_id
