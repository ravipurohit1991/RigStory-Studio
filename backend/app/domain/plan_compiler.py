"""Deterministic multi-actor motion plan compiler.

Compiles a validated :class:`MotionPlan` into one editable
:class:`AnimationClip` on the shared scene timeline. Both actors get their own
action lanes; synchronization, contacts, and the handshake primitive are solved
here — never by the model. The output is ordinary track/keyframe data plus a
validation report, and identical inputs always produce identical output.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

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
from app.domain.errors import DomainValidationError
from app.domain.ids import ClipId
from app.domain.math2d.vec2 import Vec2
from app.domain.motion import (
    MotionCompileResult,
    MotionValidationReport,
    MotionWarning,
    ValidationMetricReport,
    anchor_world_position,
    resolve_walk_path,
    solve_two_bone_ik,
)
from app.domain.motion_plan import (
    ApproachAction,
    ContactDefinition,
    GraspAction,
    HandshakeAction,
    LeanAction,
    LocomoteAction,
    LookAtAction,
    MotionPlan,
    PlannedAction,
    PlanSchedule,
    PointAction,
    ReachAction,
    ReleaseAction,
    RetreatAction,
    ScheduledAction,
    SitAction,
    TurnAction,
    WaveAction,
    schedule_plan,
)
from app.domain.scene import SceneDefinition
from app.domain.scene_queries import object_world_bounds
from app.domain.versioning import ENGINE_VERSION

# Two roots closer than this count as a body overlap (specs §17.3).
HARD_OVERLAP_DISTANCE = 0.35
# Personal-space envelope: approaches never target a smaller separation.
MIN_ACTOR_SPACING = 0.6
SHOULDER_HEIGHT = 1.35
CONTACT_HEIGHT = 1.05


@dataclass
class _ActorState:
    position: Vec2
    upper_arm: float
    lower_arm: float
    reach: float
    # (time, position) checkpoints in increasing time order.
    checkpoints: list[tuple[float, Vec2]] = field(default_factory=list)


@dataclass
class _CompileState:
    scene: SceneDefinition
    plan: MotionPlan
    actors: dict[str, _ActorState]
    scalar_keys: dict[tuple[str, str], list[ScalarKeyframe]] = field(default_factory=dict)
    root_keys: dict[str, list[VectorKeyframe]] = field(default_factory=dict)
    markers: list[ClipMarker] = field(default_factory=list)
    warnings: list[MotionWarning] = field(default_factory=list)
    max_target_error: float = 0.0

    def warn(
        self,
        code: str,
        action_id: str | None,
        message: str,
        time_range: tuple[float, float] | None = None,
    ) -> None:
        self.warnings.append(
            MotionWarning(
                code=code, action_id=action_id or None, message=message, time_range=time_range
            )
        )

    def position_at(self, actor_id: str, at_time: float) -> Vec2:
        state = self.actors[actor_id]
        position = state.checkpoints[0][1]
        for checkpoint_time, checkpoint in state.checkpoints:
            if checkpoint_time <= at_time + 1e-6:
                position = checkpoint
            else:
                break
        return position

    def move_actor(self, actor_id: str, at_time: float, position: Vec2) -> None:
        state = self.actors[actor_id]
        state.checkpoints.append((round(at_time, 4), position))
        state.position = position

    def scalar_key(
        self, actor_id: str, bone_id: str, action_id: str, time: float, value: float
    ) -> None:
        key = (actor_id, bone_id)
        keys = self.scalar_keys.setdefault(key, [])
        keys.append(
            ScalarKeyframe(
                id=f"key_{action_id}_{len(keys)}",
                time=round(time, 4),
                value=round(value, 4),
            )
        )

    def root_key(self, actor_id: str, action_id: str, time: float, position: Vec2) -> None:
        keys = self.root_keys[actor_id]
        keys.append(
            VectorKeyframe(
                id=f"key_{action_id}_root_{len(keys)}",
                time=round(time, 4),
                value=(round(position.x, 4), round(position.y, 4)),
            )
        )

    def hold_root(self, actor_id: str, action_id: str, until: float) -> None:
        """Pin the actor in place before a movement so idle gaps do not drift."""
        keys = self.root_keys[actor_id]
        if keys and keys[-1].time < round(until, 4) - 1e-6:
            self.root_key(actor_id, action_id, until, self.position_at(actor_id, until))


def _resolve_target(state: _CompileState, ref: str, at_time: float) -> Vec2 | None:
    if ref in state.actors:
        return state.position_at(ref, at_time)
    if "." in ref:
        return anchor_world_position(state.scene, ref)
    for scene_object in state.scene.objects:
        if scene_object.id == ref:
            bounds = object_world_bounds(scene_object)
            return Vec2((bounds.min_x + bounds.max_x) / 2.0, (bounds.min_y + bounds.max_y) / 2.0)
    return None


def _walk_segment(
    state: _CompileState,
    *,
    actor_id: str,
    action_id: str,
    start: float,
    duration: float,
    goal: Vec2,
    swing_amplitude: float,
) -> None:
    """Emit root path keys plus gait swings from the actor position to ``goal``."""
    origin = state.position_at(actor_id, start)
    # Pin the actor at the walk start so idle gaps and the pre-walk pose hold.
    state.hold_root(actor_id, action_id, start)
    path = resolve_walk_path(state.scene, origin, goal)
    if len(path) > 2:
        state.warn(
            "PATH_DETOUR",
            action_id,
            "root path was routed around a blocked collider",
            (start, start + duration),
        )
    total = sum(path[index].distance_to(path[index + 1]) for index in range(len(path) - 1))
    elapsed = 0.0
    for index in range(len(path) - 1):
        segment = path[index].distance_to(path[index + 1])
        elapsed += duration * (segment / total if total > 1e-9 else 1.0)
        state.root_key(actor_id, action_id, start + elapsed, path[index + 1])
    state.move_actor(actor_id, start + duration, goal)

    if total <= 1e-9 or swing_amplitude <= 0.0:
        return
    step_count = max(1, int(max(1.0, total / 0.55)))
    for step in range(step_count + 1):
        phase_time = start + duration * step / step_count
        swing = math.sin(step * math.pi) * swing_amplitude
        state.scalar_key(actor_id, "thigh_l", action_id, phase_time, swing)
        state.scalar_key(actor_id, "thigh_r", action_id, phase_time, -swing)
        state.scalar_key(actor_id, "upper_arm_l", action_id, phase_time, -swing * 0.55)
        state.scalar_key(actor_id, "upper_arm_r", action_id, phase_time, swing * 0.55)


def _arm_ik_keys(
    state: _CompileState,
    *,
    actor_id: str,
    action_id: str,
    hand: Literal["left", "right"],
    target: Vec2,
    start: float,
    raise_at: float,
    tolerance: float | None = None,
) -> float:
    """Raise one arm toward ``target`` via two-bone IK; returns the target error."""
    actor = state.actors[actor_id]
    shoulder = state.position_at(actor_id, raise_at) + Vec2(0.0, SHOULDER_HEIGHT)
    ik = solve_two_bone_ik(
        start=shoulder,
        target=target,
        upper_length=actor.upper_arm,
        lower_length=actor.lower_arm,
        bend_direction="negative" if hand == "right" else "positive",
        softness=0.02,
    )
    state.max_target_error = max(state.max_target_error, ik.target_error)
    if not ik.reachable:
        state.warn(
            "TARGET_UNREACHABLE_CLAMPED",
            action_id,
            "target is outside the arm envelope and was clamped",
            (start, raise_at),
        )
    if tolerance is not None and ik.target_error > tolerance:
        state.warn(
            "CONTACT_TOLERANCE_EXCEEDED",
            action_id,
            f"contact error {round(ik.target_error, 4)} exceeds tolerance {tolerance}",
            (start, raise_at),
        )
    suffix = "r" if hand == "right" else "l"
    state.scalar_key(actor_id, f"upper_arm_{suffix}", action_id, start, 0.0)
    state.scalar_key(actor_id, f"upper_arm_{suffix}", action_id, raise_at, ik.shoulder_rotation_deg)
    state.scalar_key(actor_id, f"forearm_{suffix}", action_id, raise_at, ik.elbow_rotation_deg)
    return ik.target_error


def _lower_arm_keys(
    state: _CompileState,
    *,
    actor_id: str,
    action_id: str,
    hand: Literal["left", "right"],
    at_time: float,
) -> None:
    suffix = "r" if hand == "right" else "l"
    state.scalar_key(actor_id, f"upper_arm_{suffix}", action_id, at_time, 0.0)
    state.scalar_key(actor_id, f"forearm_{suffix}", action_id, at_time, 0.0)


def _gaze_keys(
    state: _CompileState,
    *,
    actor_id: str,
    action_id: str,
    target: Vec2,
    start: float,
    lead_end: float,
    release_at: float | None = None,
) -> None:
    """Aim the head at ``target``; gaze leads the body (plan.md §9.5)."""
    origin = state.position_at(actor_id, start)
    angle = (target - origin).angle_deg() * 0.25
    state.scalar_key(actor_id, "head", action_id, start, 0.0)
    state.scalar_key(actor_id, "head", action_id, lead_end, angle)
    if release_at is not None:
        state.scalar_key(actor_id, "head", action_id, release_at, 0.0)


def _matching_contact(plan: MotionPlan, action: HandshakeAction) -> ContactDefinition | None:
    pair = {action.actor_id, action.partner_id}
    for contact in plan.contacts:
        if contact.kind != "hand_to_hand":
            continue
        if {contact.reference_actor_id, contact.follower_actor_id} == pair:
            return contact
    return None


def _compile_handshake(
    state: _CompileState, item: ScheduledAction, action: HandshakeAction
) -> None:
    start, end = item.start, item.end
    duration = end - start
    approach_end = round(start + duration * 0.3, 4)
    hold_end = round(start + duration * 0.85, 4)
    style = state.plan.style

    contact = _matching_contact(state.plan, action)
    reference_id = contact.reference_actor_id if contact is not None else action.actor_id
    follower_id = action.partner_id if reference_id == action.actor_id else action.actor_id
    reference_hand = contact.reference_hand if contact is not None else action.hand
    follower_hand = (
        contact.follower_hand
        if contact is not None and contact.follower_hand is not None
        else action.hand
    )
    tolerance = contact.position_tolerance if contact is not None else 0.05
    contact_slug = contact.id if contact is not None else action.id

    initiator = state.actors[action.actor_id]
    partner = state.actors[action.partner_id]
    init_pos = state.position_at(action.actor_id, start)
    partner_pos = state.position_at(action.partner_id, start)
    to_partner = partner_pos - init_pos
    direction = to_partner.normalized() if to_partner.length() > 1e-9 else Vec2(1.0, 0.0)

    combined_reach = initiator.reach + partner.reach
    desired_gap = min(
        max(0.62 * combined_reach, MIN_ACTOR_SPACING + 0.1),
        max(combined_reach - 0.1, MIN_ACTOR_SPACING + 0.1),
    )
    gap = to_partner.length()
    if gap > desired_gap + 0.02:
        # Only the initiator moves; the partner is the stationary side.
        goal = partner_pos - direction.scaled(desired_gap)
        _walk_segment(
            state,
            actor_id=action.actor_id,
            action_id=action.id,
            start=start,
            duration=approach_end - start,
            goal=goal,
            swing_amplitude=6.0 + style.energy * 6.0,
        )
        init_pos = goal
    elif gap < MIN_ACTOR_SPACING - 1e-6:
        state.warn(
            "SPACING_ADJUSTED",
            action.id,
            "actors start inside the personal-space envelope; contact solved in place",
            (start, end),
        )

    contact_point = Vec2(
        (init_pos.x + partner_pos.x) / 2.0,
        (init_pos.y + partner_pos.y) / 2.0 + CONTACT_HEIGHT,
    )

    # Reference side first (hard), follower side solved toward the same point.
    reference_error = _arm_ik_keys(
        state,
        actor_id=reference_id,
        action_id=action.id,
        hand=reference_hand,
        target=contact_point,
        start=start,
        raise_at=approach_end,
    )
    follower_error = _arm_ik_keys(
        state,
        actor_id=follower_id,
        action_id=action.id,
        hand=follower_hand,
        target=contact_point,
        start=start,
        raise_at=approach_end,
        tolerance=tolerance,
    )

    # Controlled vertical oscillation on both forearms during the hold. Both
    # sides oscillate in phase around their grip angle so the grip stays closed.
    oscillation_amp = 3.0 + style.exaggeration * 3.0
    steps = action.oscillations * 2
    for side_actor, side_hand in ((reference_id, reference_hand), (follower_id, follower_hand)):
        suffix = "r" if side_hand == "right" else "l"
        forearm_keys = state.scalar_keys.get((side_actor, f"forearm_{suffix}"), [])
        grip_angle = forearm_keys[-1].value if forearm_keys else 0.0
        for step in range(1, steps + 1):
            osc_time = approach_end + (hold_end - approach_end) * step / (steps + 1)
            offset = oscillation_amp if step % 2 == 1 else -oscillation_amp
            state.scalar_key(
                side_actor, f"forearm_{suffix}", action.id, osc_time, grip_angle + offset
            )
        state.scalar_key(side_actor, f"forearm_{suffix}", action.id, hold_end, grip_angle)

    # Social orientation: both actors look at each other, gaze leading contact.
    _gaze_keys(
        state,
        actor_id=action.actor_id,
        action_id=action.id,
        target=partner_pos,
        start=start,
        lead_end=round(start + duration * 0.15, 4),
        release_at=end,
    )
    _gaze_keys(
        state,
        actor_id=action.partner_id,
        action_id=action.id,
        target=init_pos,
        start=start,
        lead_end=round(start + duration * 0.15, 4),
        release_at=end,
    )
    for actor_id in (action.actor_id, action.partner_id):
        state.scalar_key(actor_id, "spine_upper", action.id, start, 0.0)
        state.scalar_key(actor_id, "spine_upper", action.id, approach_end, 3.0)
        state.scalar_key(actor_id, "spine_upper", action.id, end, 0.0)

    # Release and return to rest.
    _lower_arm_keys(
        state, actor_id=reference_id, action_id=action.id, hand=reference_hand, at_time=end
    )
    _lower_arm_keys(
        state, actor_id=follower_id, action_id=action.id, hand=follower_hand, at_time=end
    )

    state.markers.append(
        ClipMarker(
            name=f"{contact_slug}_contact_start", time=round(approach_end, 4), kind="contact"
        )
    )
    state.markers.append(
        ClipMarker(name=f"{contact_slug}_contact_end", time=round(hold_end, 4), kind="contact")
    )
    state.markers.append(
        ClipMarker(name=f"{action.id}_sync", time=round(approach_end, 4), kind="sync")
    )
    state.max_target_error = max(state.max_target_error, reference_error, follower_error)
    final_gap = state.position_at(action.actor_id, end).distance_to(
        state.position_at(action.partner_id, end)
    )
    if final_gap < MIN_ACTOR_SPACING - 1e-6:
        state.warn(
            "SPACING_ADJUSTED",
            action.id,
            f"handshake spacing {round(final_gap, 4)} is below the envelope",
            (start, end),
        )


def _compile_action(state: _CompileState, item: ScheduledAction) -> None:
    action: PlannedAction = item.action
    start, end = item.start, item.end
    duration = end - start
    style = state.plan.style
    actor_id = action.actor_id

    if isinstance(action, LocomoteAction | ApproachAction):
        target = _resolve_target(state, action.target_ref, start)
        if target is None:
            state.warn("UNKNOWN_TARGET", action.id, f"target {action.target_ref!r} not found")
            return
        stop_distance = action.stop_distance
        if action.target_ref in state.actors and stop_distance < MIN_ACTOR_SPACING:
            state.warn(
                "SPACING_ADJUSTED",
                action.id,
                f"stop distance raised to the personal-space envelope {MIN_ACTOR_SPACING}",
                (start, end),
            )
            stop_distance = MIN_ACTOR_SPACING
        origin = state.position_at(actor_id, start)
        to_target = target - origin
        distance = to_target.length()
        if distance <= stop_distance + 1e-6:
            state.warn(
                "APPROACH_UNNECESSARY",
                action.id,
                "actor is already within stop distance; no movement compiled",
                (start, end),
            )
            state.move_actor(actor_id, end, origin)
            return
        goal = (
            target - to_target.normalized().scaled(stop_distance) if stop_distance > 0.0 else target
        )
        # Keep out of the other actor's personal space at arrival (plan.md §9.2).
        for other_id in state.actors:
            if other_id == actor_id:
                continue
            other_pos = state.position_at(other_id, end)
            if goal.distance_to(other_pos) < MIN_ACTOR_SPACING - 1e-6:
                away = goal - other_pos
                fallback = (
                    away.normalized()
                    if away.length() > 1e-9
                    else (origin - other_pos).normalized()
                    if origin.distance_to(other_pos) > 1e-9
                    else Vec2(1.0, 0.0)
                )
                goal = other_pos + fallback.scaled(MIN_ACTOR_SPACING)
                state.warn(
                    "SPACING_ADJUSTED",
                    action.id,
                    f"arrival point moved outside the personal space of {other_id!r}",
                    (start, end),
                )
        gait_boost = 4.0 if isinstance(action, LocomoteAction) and action.gait == "brisk" else 0.0
        _walk_segment(
            state,
            actor_id=actor_id,
            action_id=action.id,
            start=start,
            duration=duration,
            goal=goal,
            swing_amplitude=8.0 + style.energy * 10.0 + gait_boost,
        )
    elif isinstance(action, RetreatAction):
        target = _resolve_target(state, action.target_ref, start)
        if target is None:
            state.warn("UNKNOWN_TARGET", action.id, f"target {action.target_ref!r} not found")
            return
        origin = state.position_at(actor_id, start)
        away = origin - target
        direction = away.normalized() if away.length() > 1e-9 else Vec2(-1.0, 0.0)
        _walk_segment(
            state,
            actor_id=actor_id,
            action_id=action.id,
            start=start,
            duration=duration,
            goal=origin + direction.scaled(action.distance),
            swing_amplitude=6.0 + style.energy * 8.0,
        )
    elif isinstance(action, TurnAction):
        origin = state.position_at(actor_id, start)
        if action.target_ref is not None:
            target = _resolve_target(state, action.target_ref, start)
            if target is None:
                state.warn("UNKNOWN_TARGET", action.id, f"target {action.target_ref!r} not found")
                return
            angle = (target - origin).angle_deg()
        else:
            angle = 180.0 if action.facing == "left" else 0.0
        state.scalar_key(actor_id, "hips", action.id, start, 0.0)
        state.scalar_key(actor_id, "hips", action.id, end, angle)
        # Gaze leads the turn (plan.md §9.5).
        state.scalar_key(actor_id, "head", action.id, start, 0.0)
        state.scalar_key(actor_id, "head", action.id, start + duration * 0.4, angle * 0.2)
        state.scalar_key(actor_id, "head", action.id, end, 0.0)
    elif isinstance(action, LookAtAction):
        target = _resolve_target(state, action.target_ref, start)
        if target is None:
            state.warn("UNKNOWN_TARGET", action.id, f"target {action.target_ref!r} not found")
            return
        _gaze_keys(
            state,
            actor_id=actor_id,
            action_id=action.id,
            target=target,
            start=start,
            lead_end=round(start + duration * 0.6, 4),
        )
        if action.posture is not None:
            state.markers.append(
                ClipMarker(name=f"{action.id}_{action.posture}", time=round(start, 4))
            )
    elif isinstance(action, ReachAction | PointAction | GraspAction):
        target = _resolve_target(state, action.target_ref, start)
        if target is None:
            state.warn("UNKNOWN_TARGET", action.id, f"target {action.target_ref!r} not found")
            return
        raise_at = round(start + duration * 0.65, 4)
        _arm_ik_keys(
            state,
            actor_id=actor_id,
            action_id=action.id,
            hand=action.hand,
            target=target,
            start=start,
            raise_at=raise_at,
        )
        state.markers.append(
            ClipMarker(
                name=f"{action.id}_{action.type}",
                time=raise_at,
                kind="contact" if action.type == "grasp" else "marker",
            )
        )
    elif isinstance(action, ReleaseAction):
        _lower_arm_keys(
            state, actor_id=actor_id, action_id=action.id, hand=action.hand, at_time=end
        )
        state.markers.append(ClipMarker(name=f"{action.id}_release", time=round(end, 4)))
    elif isinstance(action, WaveAction):
        suffix = "r" if action.hand == "right" else "l"
        amplitude = 20.0 + action.amplitude * 20.0 + style.exaggeration * 15.0
        state.scalar_key(actor_id, f"upper_arm_{suffix}", action.id, start, -35.0)
        for rep in range(action.repetitions * 2 + 1):
            phase = rep / max(1, action.repetitions * 2)
            value = -55.0 + (amplitude if rep % 2 == 0 else -amplitude)
            state.scalar_key(
                actor_id, f"forearm_{suffix}", action.id, start + duration * phase, value
            )
    elif isinstance(action, SitAction):
        target = _resolve_target(state, action.target_ref, start)
        if target is None:
            state.warn("UNKNOWN_TARGET", action.id, f"target {action.target_ref!r} not found")
            return
        origin = state.position_at(actor_id, start)
        approach = Vec2(target.x - 0.25, origin.y)
        _walk_segment(
            state,
            actor_id=actor_id,
            action_id=action.id,
            start=start,
            duration=duration * 0.45,
            goal=approach,
            swing_amplitude=6.0 + style.energy * 8.0,
        )
        state.scalar_key(actor_id, "thigh_l", action.id, start + duration * 0.55, -82.0)
        state.scalar_key(actor_id, "thigh_r", action.id, start + duration * 0.55, -82.0)
        state.scalar_key(actor_id, "shin_l", action.id, end, 82.0)
        state.scalar_key(actor_id, "shin_r", action.id, end, 82.0)
        state.markers.append(ClipMarker(name=f"{action.id}_seated", time=round(end, 4)))
    elif action.type == "rise":
        for bone_id in ("thigh_l", "thigh_r", "shin_l", "shin_r"):
            state.scalar_key(actor_id, bone_id, action.id, end, 0.0)
    elif isinstance(action, LeanAction):
        state.scalar_key(actor_id, "spine_upper", action.id, start, 0.0)
        state.scalar_key(
            actor_id, "spine_upper", action.id, start + duration * 0.5, action.amount * 12.0
        )
        state.scalar_key(actor_id, "spine_upper", action.id, end, 0.0)
    elif action.type in {"shift_weight", "crouch", "kneel"}:
        amount = getattr(action, "amount", 0.5)
        state.scalar_key(actor_id, "spine_upper", action.id, start, 0.0)
        state.scalar_key(actor_id, "spine_upper", action.id, start + duration * 0.5, amount * 8.0)
        state.scalar_key(actor_id, "spine_upper", action.id, end, 0.0)
    elif isinstance(action, HandshakeAction):
        _compile_handshake(state, item, action)
    # idle emits no keys: the actor deliberately holds the current pose.


def _sample_root(keys: list[VectorKeyframe], at_time: float) -> Vec2:
    if not keys:
        return Vec2.zero()
    previous = keys[0]
    if at_time <= previous.time:
        return Vec2(previous.value[0], previous.value[1])
    for key in keys[1:]:
        if at_time <= key.time:
            span = key.time - previous.time
            blend = (at_time - previous.time) / span if span > 1e-9 else 1.0
            return Vec2(
                previous.value[0] + (key.value[0] - previous.value[0]) * blend,
                previous.value[1] + (key.value[1] - previous.value[1]) * blend,
            )
        previous = key
    return Vec2(previous.value[0], previous.value[1])


def _actor_overlap_metrics(state: _CompileState) -> tuple[int, float]:
    actor_ids = sorted(state.root_keys)
    if len(actor_ids) < 2:
        return 0, 0.0
    left_keys = sorted(state.root_keys[actor_ids[0]], key=lambda key: key.time)
    right_keys = sorted(state.root_keys[actor_ids[1]], key=lambda key: key.time)
    times = sorted({key.time for key in (*left_keys, *right_keys)})
    penetration_frames = 0
    max_depth = 0.0
    for at_time in times:
        distance = _sample_root(left_keys, at_time).distance_to(_sample_root(right_keys, at_time))
        if distance < HARD_OVERLAP_DISTANCE:
            penetration_frames += 1
            max_depth = max(max_depth, HARD_OVERLAP_DISTANCE - distance)
    return penetration_frames, round(max_depth, 4)


def compile_motion_plan(
    *,
    scene: SceneDefinition,
    characters: dict[str, CharacterDefinition],
    plan: MotionPlan,
    clip_id: ClipId,
    clip_name: str = "Planned motion",
) -> MotionCompileResult:
    """Compile a validated plan into one editable clip plus a report."""
    schedule: PlanSchedule = schedule_plan(plan)
    if schedule.issues:
        raise DomainValidationError(tuple(schedule.issues))

    actors: dict[str, _ActorState] = {}
    for actor in scene.actors:
        character = characters.get(actor.character_id)
        lengths = (
            {bone.id: bone.length for bone in character.rig.bones} if character is not None else {}
        )
        upper = max(lengths.get("upper_arm_r", 0.45), lengths.get("upper_arm_l", 0.45))
        lower = max(lengths.get("forearm_r", 0.38), lengths.get("forearm_l", 0.38)) + max(
            lengths.get("hand_r", 0.12), lengths.get("hand_l", 0.12)
        )
        position = Vec2(actor.root_transform.position[0], actor.root_transform.position[1])
        actors[actor.id] = _ActorState(
            position=position,
            upper_arm=upper,
            lower_arm=lower,
            reach=upper + lower,
            checkpoints=[(0.0, position)],
        )

    state = _CompileState(scene=scene, plan=plan, actors=actors)
    for actor_id, actor_state in actors.items():
        state.root_keys[actor_id] = [
            VectorKeyframe(
                id=f"key_start_{actor_id.removeprefix('actor_')}",
                time=0.0,
                value=(
                    round(actor_state.position.x, 4),
                    round(actor_state.position.y, 4),
                ),
            )
        ]

    for item in sorted(schedule.actions, key=lambda entry: (entry.start, entry.action.id)):
        if item.action.actor_id not in state.actors:
            state.warn(
                "UNKNOWN_ACTOR",
                item.action.id,
                f"actor {item.action.actor_id!r} is not present in the scene",
            )
            continue
        _compile_action(state, item)

    for warning in schedule.warnings:
        state.warn(warning.code, warning.action_id or "", warning.message)

    tracks: list[Track] = []
    max_key_time = 0.0
    for actor_id in sorted(state.root_keys):
        ordered_keys = sorted(state.root_keys[actor_id], key=lambda key: key.time)
        deduped_root: list[VectorKeyframe] = []
        for vector_key in ordered_keys:
            if deduped_root and vector_key.time <= deduped_root[-1].time:
                vector_key = vector_key.model_copy(
                    update={"time": round(deduped_root[-1].time + 0.0001, 4)}
                )
            deduped_root.append(vector_key)
        max_key_time = max(max_key_time, deduped_root[-1].time if deduped_root else 0.0)
        tracks.append(
            RootTranslationTrack(
                id=f"track_{actor_id.removeprefix('actor_')}_root",
                actor_id=actor_id,
                keyframes=tuple(deduped_root),
            )
        )
    for (actor_id, bone_id), keyframes in sorted(state.scalar_keys.items()):
        ordered = sorted(keyframes, key=lambda key: key.time)
        deduped: list[ScalarKeyframe] = []
        for keyframe in ordered:
            if deduped and keyframe.time <= deduped[-1].time:
                keyframe = keyframe.model_copy(update={"time": round(deduped[-1].time + 0.0001, 4)})
            deduped.append(keyframe)
        max_key_time = max(max_key_time, deduped[-1].time if deduped else 0.0)
        tracks.append(
            BoneRotationTrack(
                id=f"track_{actor_id.removeprefix('actor_')}_{bone_id}",
                actor_id=actor_id,
                bone_id=bone_id,
                keyframes=tuple(deduped),
            )
        )

    penetration_frames, max_penetration_depth = _actor_overlap_metrics(state)
    if penetration_frames > 0:
        state.warn(
            "ACTOR_OVERLAP",
            "",
            f"actor roots overlap in {penetration_frames} sampled frame(s)",
        )

    duration = max(0.1, round(max(schedule.duration, max_key_time), 4))
    markers = tuple(sorted(state.markers, key=lambda marker: (marker.time, marker.name)))
    clip = AnimationClip(
        id=clip_id,
        scene_id=scene.id,
        name=clip_name,
        duration=duration,
        tracks=tuple(tracks),
        markers=markers,
        source_plan_id=plan.id,
        engine_version=str(ENGINE_VERSION),
    )
    status: Literal["ok", "warning", "failed"] = "warning" if state.warnings else "ok"
    report = MotionValidationReport(
        clip_id=clip.id,
        status=status,
        metrics=ValidationMetricReport(
            max_target_error=round(state.max_target_error, 4),
            penetration_frames=penetration_frames,
            max_penetration_depth=max_penetration_depth,
        ),
        warnings=tuple(state.warnings),
    )
    return MotionCompileResult(clip=clip, report=report)
