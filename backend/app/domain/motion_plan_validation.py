"""Semantic validation and feasibility checks for motion plans (plan.md §8.3, §9.6).

Structural shape is enforced by the Pydantic models in
:mod:`app.domain.motion_plan`. This module checks the plan against the scene
snapshot that was supplied to the planner: reference integrity, action-graph
health, limb exclusivity, actor count, affordance compatibility, rough
reachability, contact feasibility, and two-actor prompt ambiguity.

Errors reject the plan. Warnings ride along with the plan so the user can see
them on the action cards before compiling.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.domain.errors import ValidationIssue
from app.domain.math2d.vec2 import Vec2
from app.domain.motion_plan import (
    MAX_PLAN_ACTORS,
    ApproachAction,
    LocomoteAction,
    MotionPlanBody,
    PlannedAction,
    PlanSchedule,
    PlanWarning,
    RetreatAction,
    SitAction,
    schedule_plan,
)
from app.domain.scene_snapshot import SceneSnapshot

# Slack added to reach estimates so borderline targets warn instead of flapping.
_REACH_SLACK = 0.05
# A handshake can close this much distance on its own before contact.
_HANDSHAKE_SELF_APPROACH = 1.5

_PRONOUN_RE = re.compile(r"\b(he|she|they|him|her|them|his|hers|their)\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class PlanValidationResult:
    errors: tuple[ValidationIssue, ...]
    warnings: tuple[PlanWarning, ...]
    schedule: PlanSchedule

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass(frozen=True, slots=True)
class _SnapshotIndex:
    actor_positions: dict[str, Vec2]
    actor_reach: dict[str, float]
    object_centers: dict[str, Vec2]
    anchor_positions: dict[str, Vec2]
    affordances: dict[str, set[str]]  # anchor_ref -> affordance types


def _index_snapshot(snapshot: SceneSnapshot) -> _SnapshotIndex:
    actor_positions = {
        actor.id: Vec2(actor.position[0], actor.position[1]) for actor in snapshot.actors
    }
    actor_reach = {actor.id: actor.reach_radius for actor in snapshot.actors}
    object_centers: dict[str, Vec2] = {}
    anchor_positions: dict[str, Vec2] = {}
    affordances: dict[str, set[str]] = {}
    for scene_object in snapshot.objects:
        min_x, min_y, max_x, max_y = scene_object.bounds
        object_centers[scene_object.id] = Vec2((min_x + max_x) / 2.0, (min_y + max_y) / 2.0)
        for anchor in scene_object.anchors:
            anchor_positions[anchor.ref] = Vec2(anchor.position[0], anchor.position[1])
        for affordance in scene_object.affordances:
            if affordance.anchor_ref is not None:
                affordances.setdefault(affordance.anchor_ref, set()).add(affordance.type)
    return _SnapshotIndex(
        actor_positions=actor_positions,
        actor_reach=actor_reach,
        object_centers=object_centers,
        anchor_positions=anchor_positions,
        affordances=affordances,
    )


def _resolve_ref(index: _SnapshotIndex, ref: str) -> Vec2 | None:
    if ref in index.actor_positions:
        return index.actor_positions[ref]
    if ref in index.anchor_positions:
        return index.anchor_positions[ref]
    if ref in index.object_centers:
        return index.object_centers[ref]
    return None


def _target_ref(action: PlannedAction) -> str | None:
    ref = getattr(action, "target_ref", None)
    return ref if isinstance(ref, str) else None


def _estimate_positions_at(
    index: _SnapshotIndex,
    schedule: PlanSchedule,
    at_time: float,
) -> dict[str, Vec2]:
    """Rough deterministic per-actor position estimate at ``at_time``.

    Follows completed movement actions in schedule order. This is a planning
    estimate for feasibility checks, not the compiled trajectory.
    """
    positions = dict(index.actor_positions)
    for item in sorted(schedule.actions, key=lambda entry: (entry.start, entry.action.id)):
        if item.end > at_time + 1e-6:
            continue
        action = item.action
        current = positions.get(action.actor_id)
        if current is None:
            continue
        if isinstance(action, LocomoteAction | ApproachAction):
            target = _resolve_ref(index, action.target_ref)
            if target is None:
                continue
            stop = action.stop_distance
            to_target = target - current
            distance = to_target.length()
            if distance <= stop or distance <= 1e-9:
                continue
            positions[action.actor_id] = target - to_target.normalized().scaled(stop)
        elif isinstance(action, RetreatAction):
            target = _resolve_ref(index, action.target_ref)
            if target is None:
                continue
            away = current - target
            direction = away.normalized() if away.length() > 1e-9 else Vec2(1.0, 0.0)
            positions[action.actor_id] = current + direction.scaled(action.distance)
        elif isinstance(action, SitAction):
            target = _resolve_ref(index, action.target_ref)
            if target is not None:
                positions[action.actor_id] = Vec2(target.x - 0.25, current.y)
    return positions


def validate_motion_plan(plan: MotionPlanBody, snapshot: SceneSnapshot) -> PlanValidationResult:
    errors: list[ValidationIssue] = []
    warnings: list[PlanWarning] = []
    index = _index_snapshot(snapshot)
    known_actor_ids = set(index.actor_positions)

    plan_actor_ids: set[str] = set()
    for position, action in enumerate(plan.actions):
        path = f"actions[{position}]"
        plan_actor_ids.add(action.actor_id)
        if action.actor_id not in known_actor_ids:
            errors.append(
                ValidationIssue(
                    "PLAN_UNKNOWN_ACTOR",
                    f"action {action.id!r} references actor {action.actor_id!r} "
                    "which is not in the scene",
                    f"{path}.actor_id",
                )
            )
        if action.type == "handshake":
            plan_actor_ids.add(action.partner_id)
            if action.partner_id not in known_actor_ids:
                errors.append(
                    ValidationIssue(
                        "PLAN_UNKNOWN_ACTOR",
                        f"handshake {action.id!r} references unknown partner {action.partner_id!r}",
                        f"{path}.partner_id",
                    )
                )
            elif action.partner_id == action.actor_id:
                errors.append(
                    ValidationIssue(
                        "PLAN_SELF_HANDSHAKE",
                        f"handshake {action.id!r} needs two different actors",
                        f"{path}.partner_id",
                    )
                )
        ref = _target_ref(action)
        if ref is not None and _resolve_ref(index, ref) is None:
            errors.append(
                ValidationIssue(
                    "PLAN_UNKNOWN_TARGET",
                    f"action {action.id!r} references unknown target {ref!r}; "
                    "only ids present in the scene snapshot may be used",
                    f"{path}.target_ref",
                )
            )
        if (
            action.type == "sit"
            and ref is not None
            and "sit" not in index.affordances.get(ref, set())
        ):
            errors.append(
                ValidationIssue(
                    "PLAN_AFFORDANCE_MISMATCH",
                    f"action {action.id!r} sits on {ref!r} which has no sit affordance",
                    f"{path}.target_ref",
                )
            )
        if (
            action.type == "grasp"
            and ref is not None
            and ref in index.anchor_positions
            and "grasp" not in index.affordances.get(ref, set())
        ):
            warnings.append(
                PlanWarning(
                    code="AFFORDANCE_MISSING",
                    message=f"target {ref!r} has no grasp affordance",
                    action_id=action.id,
                )
            )

    if len(plan_actor_ids) > MAX_PLAN_ACTORS:
        errors.append(
            ValidationIssue(
                "PLAN_TOO_MANY_ACTORS",
                f"plan references {len(plan_actor_ids)} actors; the maximum is {MAX_PLAN_ACTORS}",
                "actions",
            )
        )

    for position, contact in enumerate(plan.contacts):
        path = f"contacts[{position}]"
        for field_name, actor_id in (
            ("reference_actor_id", contact.reference_actor_id),
            ("follower_actor_id", contact.follower_actor_id),
        ):
            if actor_id is not None and actor_id not in known_actor_ids:
                errors.append(
                    ValidationIssue(
                        "PLAN_UNKNOWN_ACTOR",
                        f"contact {contact.id!r} references unknown actor {actor_id!r}",
                        f"{path}.{field_name}",
                    )
                )
        if contact.target_ref is not None and _resolve_ref(index, contact.target_ref) is None:
            errors.append(
                ValidationIssue(
                    "PLAN_UNKNOWN_TARGET",
                    f"contact {contact.id!r} references unknown target {contact.target_ref!r}",
                    f"{path}.target_ref",
                )
            )

    # Handedness consistency between handshake actions and their contacts
    # (plan.md §9.6).
    contacts_by_pair = {
        frozenset((contact.reference_actor_id, contact.follower_actor_id or "")): contact
        for contact in plan.contacts
        if contact.kind == "hand_to_hand"
    }
    for action in plan.actions:
        if action.type != "handshake":
            continue
        pair_contact = contacts_by_pair.get(frozenset((action.actor_id, action.partner_id)))
        if pair_contact is None:
            continue
        hands = {pair_contact.reference_hand, pair_contact.follower_hand}
        if action.hand not in hands:
            errors.append(
                ValidationIssue(
                    "PLAN_HANDEDNESS_MISMATCH",
                    f"handshake {action.id!r} uses the {action.hand} hand but contact "
                    f"{pair_contact.id!r} specifies {sorted(hand for hand in hands if hand)}",
                    "contacts",
                )
            )

    schedule = schedule_plan(plan)
    errors.extend(schedule.issues)
    warnings.extend(schedule.warnings)
    if any(issue.code == "PLAN_CYCLE" for issue in schedule.issues):
        return PlanValidationResult(tuple(errors), tuple(warnings), schedule)

    # Rough reachability for hand-target actions (plan.md §8.3). The compiler
    # clamps unreachable targets, so these are warnings rather than rejections.
    for item in schedule.actions:
        action = item.action
        if action.type not in {"reach", "point", "grasp"}:
            continue
        ref = _target_ref(action)
        if ref is None:
            continue
        target = _resolve_ref(index, ref)
        if target is None:
            continue
        positions = _estimate_positions_at(index, schedule, item.start)
        actor_position = positions.get(action.actor_id)
        reach = index.actor_reach.get(action.actor_id, 1.0)
        if actor_position is None:
            continue
        # Hand targets are reached from shoulder height, not the root.
        shoulder = actor_position + Vec2(0.0, 1.35)
        if shoulder.distance_to(target) > reach + _REACH_SLACK:
            warnings.append(
                PlanWarning(
                    code="TARGET_MAY_BE_UNREACHABLE",
                    message=(
                        f"target {ref!r} is estimated "
                        f"{round(shoulder.distance_to(target), 2)} units from the "
                        f"{action.actor_id!r} hand envelope (reach {reach})"
                    ),
                    action_id=action.id,
                )
            )

    # Contact feasibility before full compile (plan.md §9.6).
    for item in schedule.actions:
        action = item.action
        if action.type != "handshake":
            continue
        if action.partner_id not in known_actor_ids or action.actor_id not in known_actor_ids:
            continue
        positions = _estimate_positions_at(index, schedule, item.start)
        left = positions.get(action.actor_id)
        right = positions.get(action.partner_id)
        if left is None or right is None:
            continue
        combined_reach = index.actor_reach.get(action.actor_id, 1.0) + index.actor_reach.get(
            action.partner_id, 1.0
        )
        if left.distance_to(right) > combined_reach + _HANDSHAKE_SELF_APPROACH:
            errors.append(
                ValidationIssue(
                    "PLAN_CONTACT_INFEASIBLE",
                    f"handshake {action.id!r} starts with the actors "
                    f"{round(left.distance_to(right), 2)} units apart, beyond the "
                    "combined reach plus approach allowance; add an approach action",
                    "actions",
                )
            )

    # Pronoun ambiguity for two-actor prompts (plan.md §9.6). Drafts carry no
    # prompt; the persisted MotionPlan does.
    prompt: object = getattr(plan, "prompt", "")
    if isinstance(prompt, str) and prompt and len(known_actor_ids) == 2:
        named = sum(
            1
            for actor in snapshot.actors
            if actor.display_name and actor.display_name.lower() in prompt.lower()
        )
        if _PRONOUN_RE.search(prompt) and named < 2:
            warnings.append(
                PlanWarning(
                    code="PRONOUN_AMBIGUITY",
                    message=(
                        "the prompt uses pronouns without naming both actors; "
                        "verify each action is assigned to the intended actor"
                    ),
                )
            )

    return PlanValidationResult(tuple(errors), tuple(warnings), schedule)


def summarize_issues(issues: tuple[ValidationIssue, ...]) -> tuple[str, ...]:
    """Readable diagnostics for repair prompts and API error payloads."""
    return tuple(str(issue) for issue in issues)
