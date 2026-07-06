"""Deterministic motion engine for programmatic action parameters.

This module is deliberately model-free: callers provide typed action
parameters, and the compiler produces ordinary editable animation tracks plus a
validation report. The algorithms are simple kinematic foundations for
not raw frame generation and not LLM-authored animation.
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import Field

from app.domain.character import CharacterDefinition
from app.domain.clip import (
    AnimationClip,
    BoneRotationTrack,
    ClipMarker,
    RootTranslationTrack,
    ScalarKeyframe,
    Track,
    VectorKeyframe,
)
from app.domain.common import DomainModel, Point2
from app.domain.ids import ActionId, ActorId, AnchorRef, BoneId, ClipId, split_anchor_ref
from app.domain.math2d.angles import normalize_deg, shortest_delta_deg
from app.domain.math2d.vec2 import Vec2
from app.domain.scene import ActorInstance, SceneDefinition
from app.domain.scene_queries import object_world_bounds, sweep_query
from app.domain.versioning import ENGINE_VERSION

ENGINE_NAME = f"rigstory-motion-{ENGINE_VERSION}"


class MotionStyle(DomainModel):
    energy: float = Field(default=0.35, ge=0.0, le=1.0)
    tempo: float = Field(default=1.0, gt=0.0, le=3.0)
    confidence: float = Field(default=0.65, ge=0.0, le=1.0)
    exaggeration: float = Field(default=0.2, ge=0.0, le=1.0)
    tension: float = Field(default=0.2, ge=0.0, le=1.0)


class MotionAction(DomainModel):
    id: ActionId
    type: Literal[
        "idle",
        "stand",
        "shift_weight",
        "locomote",
        "turn",
        "look_at",
        "reach",
        "point",
        "wave",
        "grasp",
        "release",
        "sit",
        "rise",
        "crouch",
        "kneel",
        "lean",
        "approach",
        "retreat",
    ]
    duration: float = Field(default=1.0, gt=0.0, le=60.0)
    target: Point2 | None = None
    anchor_ref: AnchorRef | None = None
    amount: float = 1.0
    hand: Literal["left", "right"] = "right"
    repetitions: int = Field(default=1, ge=1, le=12)


class ConstraintTimeRange(DomainModel):
    start: float = Field(ge=0.0)
    end: float = Field(gt=0.0)


class ConstraintWeight(DomainModel):
    value: float = Field(ge=0.0, le=1.0)
    time_range: ConstraintTimeRange | None = None


class JointLimitConstraint(DomainModel):
    type: Literal["joint_limit"] = "joint_limit"
    bone_id: BoneId
    min_rotation_deg: float
    max_rotation_deg: float
    weight: ConstraintWeight = ConstraintWeight(value=1.0)


class LookAtConstraint(DomainModel):
    type: Literal["look_at"] = "look_at"
    bone_id: BoneId = "head"
    target: Point2
    weight: ConstraintWeight = ConstraintWeight(value=1.0)


class PositionTargetConstraint(DomainModel):
    type: Literal["position_target"] = "position_target"
    effector_id: BoneId
    target: Point2
    weight: ConstraintWeight = ConstraintWeight(value=1.0)


class OrientationTargetConstraint(DomainModel):
    type: Literal["orientation_target"] = "orientation_target"
    bone_id: BoneId
    rotation_deg: float
    weight: ConstraintWeight = ConstraintWeight(value=1.0)


class TwoBoneIkResult(DomainModel):
    start: Point2
    elbow: Point2
    end: Point2
    target: Point2
    reachable: bool
    clamped: bool
    target_error: float
    shoulder_rotation_deg: float
    elbow_rotation_deg: float


class ValidationMetricReport(DomainModel):
    max_joint_limit_violation_deg: float = 0.0
    max_foot_slide: float = 0.0
    max_target_error: float = 0.0
    penetration_frames: int = 0
    max_penetration_depth: float = 0.0
    curve_reduction_error: float = 0.0


class MotionWarning(DomainModel):
    code: str
    action_id: ActionId | None = None
    message: str
    time_range: Point2 | None = None


class MotionValidationReport(DomainModel):
    clip_id: ClipId
    status: Literal["ok", "warning", "failed"]
    metrics: ValidationMetricReport
    warnings: tuple[MotionWarning, ...] = ()


class MotionCompileResult(DomainModel):
    clip: AnimationClip
    report: MotionValidationReport
    engine_version: str = str(ENGINE_VERSION)


def solve_two_bone_ik(
    *,
    start: Vec2,
    target: Vec2,
    upper_length: float,
    lower_length: float,
    bend_direction: Literal["positive", "negative"] = "positive",
    softness: float = 0.0,
) -> TwoBoneIkResult:
    if upper_length <= 0.0 or lower_length <= 0.0:
        raise ValueError("IK segment lengths must be positive")
    to_target = target - start
    distance = to_target.length()
    max_reach = upper_length + lower_length
    min_reach = abs(upper_length - lower_length)
    soft_margin = max(0.0, softness)
    clamped_distance = max(min_reach, min(max_reach - soft_margin, distance))
    reachable = min_reach <= distance <= max_reach
    clamped = abs(clamped_distance - distance) > 1e-9
    direction = Vec2(1.0, 0.0) if distance <= 1e-9 else to_target.normalized()
    end = start + direction.scaled(clamped_distance)
    along = (
        upper_length * upper_length
        - lower_length * lower_length
        + clamped_distance * clamped_distance
    ) / (2.0 * max(clamped_distance, 1e-9))
    height_sq = max(0.0, upper_length * upper_length - along * along)
    height = math.sqrt(height_sq)
    normal = direction.perpendicular()
    if bend_direction == "negative":
        normal = normal.scaled(-1.0)
    elbow = start + direction.scaled(along) + normal.scaled(height)
    upper_vec = elbow - start
    lower_vec = end - elbow
    return TwoBoneIkResult(
        start=(start.x, start.y),
        elbow=(elbow.x, elbow.y),
        end=(end.x, end.y),
        target=(target.x, target.y),
        reachable=reachable,
        clamped=clamped,
        target_error=end.distance_to(target),
        shoulder_rotation_deg=normalize_deg(upper_vec.angle_deg()),
        elbow_rotation_deg=normalize_deg(
            shortest_delta_deg(upper_vec.angle_deg(), lower_vec.angle_deg())
        ),
    )


def _anchor_position(scene: SceneDefinition, anchor_ref: str) -> Vec2 | None:
    object_id, anchor_id = split_anchor_ref(anchor_ref)
    for scene_object in scene.objects:
        if scene_object.id != object_id:
            continue
        matrix = scene_object.transform.to_transform2d().to_affine()
        for anchor in scene_object.anchors:
            if anchor.id == anchor_id:
                return matrix.apply_point(Vec2(anchor.position[0], anchor.position[1]))
    return None


def anchor_world_position(scene: SceneDefinition, anchor_ref: str) -> Vec2 | None:
    """World position of ``"object.anchor"`` in ``scene``, or None when missing."""
    return _anchor_position(scene, anchor_ref)


def resolve_walk_path(scene: SceneDefinition, start: Vec2, end: Vec2) -> tuple[Vec2, ...]:
    """Root path from ``start`` to ``end`` with the deterministic blocked-collider detour."""
    return _walk_path(scene, start, end)


def _actor(scene: SceneDefinition, actor_id: str) -> ActorInstance:
    for actor in scene.actors:
        if actor.id == actor_id:
            return actor
    raise ValueError(f"actor {actor_id!r} is not present in scene {scene.id!r}")


def _character_lengths(character: CharacterDefinition) -> dict[str, float]:
    return {bone.id: bone.length for bone in character.rig.bones}


def _track_id(actor_id: str, name: str) -> str:
    return f"track_{actor_id.removeprefix('actor_')}_{name}"


def _key_id(action_id: str, index: int) -> str:
    return f"key_{action_id}_{index}"


def _append_scalar(
    tracks: dict[tuple[str, str], list[ScalarKeyframe]],
    *,
    actor_id: str,
    bone_id: str,
    action_id: str,
    time: float,
    value: float,
) -> None:
    key = (actor_id, bone_id)
    tracks.setdefault(key, []).append(
        ScalarKeyframe(
            id=_key_id(action_id, len(tracks.get(key, []))),
            time=round(time, 4),
            value=round(value, 4),
        )
    )


def _walk_path(scene: SceneDefinition, start: Vec2, end: Vec2) -> tuple[Vec2, ...]:
    hit = sweep_query(scene, start, end, radius=0.22)
    if hit is None:
        return (start, end)
    obstacle = next(
        (scene_object for scene_object in scene.objects if scene_object.id == hit.object_id), None
    )
    if obstacle is None:
        return (start, end)
    bounds = object_world_bounds(obstacle)
    detour_y = bounds.max_y + 0.65
    return (start, Vec2(start.x, detour_y), Vec2(end.x, detour_y), end)


def _add_root_path(
    keys: list[VectorKeyframe],
    *,
    action_id: str,
    start_time: float,
    duration: float,
    path: tuple[Vec2, ...],
) -> None:
    if len(path) == 1:
        keys.append(
            VectorKeyframe(
                id=_key_id(action_id, len(keys)), time=start_time, value=(path[0].x, path[0].y)
            )
        )
        return
    total = sum(path[index].distance_to(path[index + 1]) for index in range(len(path) - 1))
    elapsed = 0.0
    keys.append(
        VectorKeyframe(
            id=_key_id(action_id, len(keys)),
            time=round(start_time, 4),
            value=(path[0].x, path[0].y),
        )
    )
    for index in range(len(path) - 1):
        segment = path[index].distance_to(path[index + 1])
        elapsed += duration * (segment / total if total > 1e-9 else 1.0)
        point = path[index + 1]
        keys.append(
            VectorKeyframe(
                id=_key_id(action_id, len(keys)),
                time=round(start_time + elapsed, 4),
                value=(round(point.x, 4), round(point.y, 4)),
            )
        )


def compile_motion_actions(
    *,
    scene: SceneDefinition,
    actor_id: ActorId,
    character: CharacterDefinition,
    actions: tuple[MotionAction, ...],
    clip_id: ClipId,
    clip_name: str = "Programmatic motion",
    style: MotionStyle | None = None,
) -> MotionCompileResult:
    style = style or MotionStyle()
    actor = _actor(scene, actor_id)
    current = Vec2(actor.root_transform.position[0], actor.root_transform.position[1])
    root_keys: list[VectorKeyframe] = [
        VectorKeyframe(id="key_root_0", time=0.0, value=(round(current.x, 4), round(current.y, 4)))
    ]
    scalar_tracks: dict[tuple[str, str], list[ScalarKeyframe]] = {}
    markers: list[ClipMarker] = []
    warnings: list[MotionWarning] = []
    max_target_error = 0.0
    time = 0.0
    lengths = _character_lengths(character)
    upper = max(lengths.get("upper_arm_r", 0.45), lengths.get("upper_arm_l", 0.45))
    lower = max(lengths.get("forearm_r", 0.38), lengths.get("forearm_l", 0.38)) + max(
        lengths.get("hand_r", 0.12), lengths.get("hand_l", 0.12)
    )

    for action in actions:
        duration = action.duration / style.tempo
        target = Vec2(*action.target) if action.target is not None else None
        if action.anchor_ref is not None:
            anchor = _anchor_position(scene, action.anchor_ref)
            if anchor is None:
                warnings.append(
                    MotionWarning(
                        code="UNKNOWN_ANCHOR",
                        action_id=action.id,
                        message=f"anchor {action.anchor_ref!r} was not found",
                        time_range=(time, time + duration),
                    )
                )
            else:
                target = anchor

        if action.type in {"locomote", "approach"} and target is not None:
            path = _walk_path(scene, current, target)
            if len(path) > 2:
                warnings.append(
                    MotionWarning(
                        code="PATH_DETOUR",
                        action_id=action.id,
                        message="root path was routed around a blocked collider",
                        time_range=(time, time + duration),
                    )
                )
            _add_root_path(
                root_keys, action_id=action.id, start_time=time, duration=duration, path=path
            )
            current = target
            step_count = max(1, int(max(1.0, current.distance_to(path[0]) / 0.55)))
            for step in range(step_count + 1):
                phase_time = time + duration * step / step_count
                swing = math.sin(step * math.pi) * (8.0 + style.energy * 10.0)
                _append_scalar(
                    scalar_tracks,
                    actor_id=actor_id,
                    bone_id="thigh_l",
                    action_id=action.id,
                    time=phase_time,
                    value=swing,
                )
                _append_scalar(
                    scalar_tracks,
                    actor_id=actor_id,
                    bone_id="thigh_r",
                    action_id=action.id,
                    time=phase_time,
                    value=-swing,
                )
                _append_scalar(
                    scalar_tracks,
                    actor_id=actor_id,
                    bone_id="upper_arm_l",
                    action_id=action.id,
                    time=phase_time,
                    value=-swing * 0.55,
                )
                _append_scalar(
                    scalar_tracks,
                    actor_id=actor_id,
                    bone_id="upper_arm_r",
                    action_id=action.id,
                    time=phase_time,
                    value=swing * 0.55,
                )
        elif action.type == "retreat" and target is not None:
            away = current + (current - target).normalized().scaled(abs(action.amount))
            path = _walk_path(scene, current, away)
            _add_root_path(
                root_keys, action_id=action.id, start_time=time, duration=duration, path=path
            )
            current = away
        elif action.type == "turn" and target is not None:
            angle = (target - current).angle_deg()
            _append_scalar(
                scalar_tracks,
                actor_id=actor_id,
                bone_id="hips",
                action_id=action.id,
                time=time,
                value=0.0,
            )
            _append_scalar(
                scalar_tracks,
                actor_id=actor_id,
                bone_id="hips",
                action_id=action.id,
                time=time + duration,
                value=angle,
            )
        elif action.type in {"reach", "point", "grasp"} and target is not None:
            ik = solve_two_bone_ik(
                start=current + Vec2(0.0, 1.35),
                target=target,
                upper_length=upper,
                lower_length=lower,
                bend_direction="negative" if action.hand == "right" else "positive",
                softness=0.02,
            )
            max_target_error = max(max_target_error, ik.target_error)
            if not ik.reachable:
                warnings.append(
                    MotionWarning(
                        code="TARGET_UNREACHABLE_CLAMPED",
                        action_id=action.id,
                        message="reach target is outside the arm envelope and was clamped",
                        time_range=(time, time + duration),
                    )
                )
            suffix = "r" if action.hand == "right" else "l"
            _append_scalar(
                scalar_tracks,
                actor_id=actor_id,
                bone_id=f"upper_arm_{suffix}",
                action_id=action.id,
                time=time,
                value=0.0,
            )
            _append_scalar(
                scalar_tracks,
                actor_id=actor_id,
                bone_id=f"upper_arm_{suffix}",
                action_id=action.id,
                time=time + duration * 0.65,
                value=ik.shoulder_rotation_deg,
            )
            _append_scalar(
                scalar_tracks,
                actor_id=actor_id,
                bone_id=f"forearm_{suffix}",
                action_id=action.id,
                time=time + duration * 0.65,
                value=ik.elbow_rotation_deg,
            )
            markers.append(
                ClipMarker(
                    name=f"{action.id}_{action.type}",
                    time=round(time + duration * 0.65, 4),
                    kind="contact" if action.type == "grasp" else "marker",
                )
            )
        elif action.type == "wave":
            suffix = "r" if action.hand == "right" else "l"
            amplitude = 20.0 + abs(action.amount) * 20.0 + style.exaggeration * 15.0
            _append_scalar(
                scalar_tracks,
                actor_id=actor_id,
                bone_id=f"upper_arm_{suffix}",
                action_id=action.id,
                time=time,
                value=-35.0,
            )
            for rep in range(action.repetitions * 2 + 1):
                phase = rep / max(1, action.repetitions * 2)
                value = -55.0 + (amplitude if rep % 2 == 0 else -amplitude)
                _append_scalar(
                    scalar_tracks,
                    actor_id=actor_id,
                    bone_id=f"forearm_{suffix}",
                    action_id=action.id,
                    time=time + duration * phase,
                    value=value,
                )
        elif action.type == "sit" and target is not None:
            approach = Vec2(target.x - 0.25, target.y)
            _add_root_path(
                root_keys,
                action_id=action.id,
                start_time=time,
                duration=duration * 0.45,
                path=_walk_path(scene, current, approach),
            )
            current = approach
            _append_scalar(
                scalar_tracks,
                actor_id=actor_id,
                bone_id="thigh_l",
                action_id=action.id,
                time=time + duration * 0.55,
                value=-82.0,
            )
            _append_scalar(
                scalar_tracks,
                actor_id=actor_id,
                bone_id="thigh_r",
                action_id=action.id,
                time=time + duration * 0.55,
                value=-82.0,
            )
            _append_scalar(
                scalar_tracks,
                actor_id=actor_id,
                bone_id="shin_l",
                action_id=action.id,
                time=time + duration,
                value=82.0,
            )
            _append_scalar(
                scalar_tracks,
                actor_id=actor_id,
                bone_id="shin_r",
                action_id=action.id,
                time=time + duration,
                value=82.0,
            )
            markers.append(
                ClipMarker(
                    name=f"{action.id}_seated", time=round(time + duration, 4), kind="marker"
                )
            )
        elif action.type == "rise":
            _append_scalar(
                scalar_tracks,
                actor_id=actor_id,
                bone_id="thigh_l",
                action_id=action.id,
                time=time + duration,
                value=0.0,
            )
            _append_scalar(
                scalar_tracks,
                actor_id=actor_id,
                bone_id="thigh_r",
                action_id=action.id,
                time=time + duration,
                value=0.0,
            )
            _append_scalar(
                scalar_tracks,
                actor_id=actor_id,
                bone_id="shin_l",
                action_id=action.id,
                time=time + duration,
                value=0.0,
            )
            _append_scalar(
                scalar_tracks,
                actor_id=actor_id,
                bone_id="shin_r",
                action_id=action.id,
                time=time + duration,
                value=0.0,
            )
        elif action.type in {"look_at"} and target is not None:
            _append_scalar(
                scalar_tracks,
                actor_id=actor_id,
                bone_id="head",
                action_id=action.id,
                time=time,
                value=0.0,
            )
            _append_scalar(
                scalar_tracks,
                actor_id=actor_id,
                bone_id="head",
                action_id=action.id,
                time=time + duration,
                value=(target - current).angle_deg() * 0.25,
            )
        elif action.type in {"shift_weight", "lean", "crouch", "kneel"}:
            value = action.amount * (12.0 if action.type == "lean" else 8.0)
            _append_scalar(
                scalar_tracks,
                actor_id=actor_id,
                bone_id="torso",
                action_id=action.id,
                time=time,
                value=0.0,
            )
            _append_scalar(
                scalar_tracks,
                actor_id=actor_id,
                bone_id="torso",
                action_id=action.id,
                time=time + duration * 0.5,
                value=value,
            )
            _append_scalar(
                scalar_tracks,
                actor_id=actor_id,
                bone_id="torso",
                action_id=action.id,
                time=time + duration,
                value=0.0,
            )
        time += duration

    duration = max(0.1, round(time, 4))
    tracks: list[Track] = [
        RootTranslationTrack(
            id=_track_id(actor_id, "root"), actor_id=actor_id, keyframes=tuple(root_keys)
        )
    ]
    for (track_actor_id, bone_id), keyframes in sorted(scalar_tracks.items()):
        ordered = sorted(keyframes, key=lambda key: key.time)
        deduped: list[ScalarKeyframe] = []
        for keyframe in ordered:
            if deduped and keyframe.time <= deduped[-1].time:
                keyframe = keyframe.model_copy(update={"time": round(deduped[-1].time + 0.0001, 4)})
            deduped.append(keyframe)
        tracks.append(
            BoneRotationTrack(
                id=_track_id(track_actor_id, bone_id),
                actor_id=track_actor_id,
                bone_id=bone_id,
                keyframes=tuple(deduped),
            )
        )

    clip = AnimationClip(
        id=clip_id,
        scene_id=scene.id,
        name=clip_name,
        duration=duration,
        tracks=tuple(tracks),
        markers=tuple(sorted(markers, key=lambda marker: marker.time)),
    )
    status: Literal["ok", "warning", "failed"] = "warning" if warnings else "ok"
    report = MotionValidationReport(
        clip_id=clip.id,
        status=status,
        metrics=ValidationMetricReport(max_target_error=round(max_target_error, 4)),
        warnings=tuple(warnings),
    )
    return MotionCompileResult(clip=clip, report=report)
