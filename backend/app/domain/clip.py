"""Animation clip: typed tracks, keyframes, events, and markers.

Rotation values are counterclockwise degrees; rotation interpolation follows
the shortest arc. Keyframe times are seconds from clip start and strictly
increase within a track.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from app.domain.common import DomainModel, Point2
from app.domain.errors import ValidationIssue
from app.domain.ids import ActorId, BoneId, ClipId, KeyframeId, PlanId, SceneId, TrackId

type Interpolation = Literal["stepped", "linear", "cubic"]


class ScalarKeyframe(DomainModel):
    id: KeyframeId
    time: float = Field(ge=0.0)
    value: float
    interpolation: Interpolation = "linear"


class VectorKeyframe(DomainModel):
    id: KeyframeId
    time: float = Field(ge=0.0)
    value: Point2
    interpolation: Interpolation = "linear"


class BoneRotationTrack(DomainModel):
    type: Literal["bone_rotation"] = "bone_rotation"
    id: TrackId
    actor_id: ActorId
    bone_id: BoneId
    keyframes: tuple[ScalarKeyframe, ...] = ()


class RootTranslationTrack(DomainModel):
    type: Literal["root_translation"] = "root_translation"
    id: TrackId
    actor_id: ActorId
    keyframes: tuple[VectorKeyframe, ...] = ()


class BoneScaleTrack(DomainModel):
    type: Literal["bone_scale"] = "bone_scale"
    id: TrackId
    actor_id: ActorId
    bone_id: BoneId
    keyframes: tuple[VectorKeyframe, ...] = ()


class ConstraintWeightTrack(DomainModel):
    type: Literal["constraint_weight"] = "constraint_weight"
    id: TrackId
    actor_id: ActorId
    constraint_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    keyframes: tuple[ScalarKeyframe, ...] = ()


type Track = Annotated[
    BoneRotationTrack | RootTranslationTrack | BoneScaleTrack | ConstraintWeightTrack,
    Field(discriminator="type"),
]


class ClipEvent(DomainModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    time: float = Field(ge=0.0)
    params: dict[str, str | float | bool] = Field(default_factory=dict)


class ClipMarker(DomainModel):
    name: str = Field(min_length=1)
    time: float = Field(ge=0.0)
    kind: Literal["marker", "contact", "sync"] = "marker"


class AnimationClip(DomainModel):
    id: ClipId
    scene_id: SceneId
    name: str = Field(min_length=1)
    duration: float = Field(gt=0.0)
    loop: bool = False
    loop_range: Point2 | None = None
    tracks: tuple[Track, ...] = ()
    events: tuple[ClipEvent, ...] = ()
    markers: tuple[ClipMarker, ...] = ()
    # Set when the clip was compiled from a motion plan: the clip
    # stays ordinary editable data, but recompiles know their origin.
    source_plan_id: PlanId | None = None
    engine_version: str | None = None


def validate_clip(clip: AnimationClip, path_prefix: str = "") -> list[ValidationIssue]:
    prefix = f"{path_prefix}." if path_prefix else ""
    issues: list[ValidationIssue] = []

    if clip.loop_range is not None:
        start, end = clip.loop_range
        if start < 0.0 or end < 0.0 or start >= end or end > clip.duration:
            issues.append(
                ValidationIssue(
                    "CLIP_LOOP_RANGE_INVALID",
                    "loop_range must be [start, end] with 0 <= start < end <= duration",
                    f"{prefix}loop_range",
                )
            )

    seen_track_ids: set[str] = set()
    for track_index, track in enumerate(clip.tracks):
        track_path = f"{prefix}tracks[{track_index}]"
        if track.id in seen_track_ids:
            issues.append(
                ValidationIssue(
                    "CLIP_DUPLICATE_TRACK_ID",
                    f"track id {track.id!r} is defined more than once",
                    f"{track_path}.id",
                )
            )
        seen_track_ids.add(track.id)

        seen_key_ids: set[str] = set()
        previous_time: float | None = None
        keyframes: tuple[ScalarKeyframe | VectorKeyframe, ...] = track.keyframes
        for key_index, keyframe in enumerate(keyframes):
            key_path = f"{track_path}.keyframes[{key_index}]"
            if keyframe.id in seen_key_ids:
                issues.append(
                    ValidationIssue(
                        "CLIP_DUPLICATE_KEYFRAME_ID",
                        f"keyframe id {keyframe.id!r} appears twice in track {track.id!r}",
                        f"{key_path}.id",
                    )
                )
            seen_key_ids.add(keyframe.id)
            if previous_time is not None and keyframe.time <= previous_time:
                issues.append(
                    ValidationIssue(
                        "CLIP_KEYFRAME_ORDER",
                        f"keyframe times must strictly increase in track {track.id!r}: "
                        f"{keyframe.time} follows {previous_time}",
                        f"{key_path}.time",
                    )
                )
            previous_time = keyframe.time
            if keyframe.time > clip.duration:
                issues.append(
                    ValidationIssue(
                        "CLIP_KEYFRAME_OUT_OF_RANGE",
                        f"keyframe at {keyframe.time}s exceeds clip duration "
                        f"{clip.duration}s in track {track.id!r}",
                        f"{key_path}.time",
                    )
                )

    for event_index, event in enumerate(clip.events):
        if event.time > clip.duration:
            issues.append(
                ValidationIssue(
                    "CLIP_EVENT_OUT_OF_RANGE",
                    f"event {event.name!r} at {event.time}s exceeds clip duration",
                    f"{prefix}events[{event_index}].time",
                )
            )
    for marker_index, marker in enumerate(clip.markers):
        if marker.time > clip.duration:
            issues.append(
                ValidationIssue(
                    "CLIP_MARKER_OUT_OF_RANGE",
                    f"marker {marker.name!r} at {marker.time}s exceeds clip duration",
                    f"{prefix}markers[{marker_index}].time",
                )
            )
    return issues
