"""Motion plan contract: the second major LLM output (specs §19).

A ``MotionPlan`` is a semantic action graph, never frames or code. The model
returns a :class:`MotionPlanDraft`; the application mints the stable
:class:`MotionPlan` identity and persists it in the project document. Every
reference (actors, objects, anchors) must resolve against the scene snapshot
that was supplied to the model — unknown references reject the plan instead of
fabricating scene content.

Scheduling (plan.md §9.1) also lives here: the shared scene timeline, per-actor
action lanes, synchronization constraints, and actor resource conflicts are
resolved deterministically from the plan alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.domain.character import CharacterDefinition
from app.domain.common import DomainModel
from app.domain.errors import ValidationIssue
from app.domain.ids import ActionId, ActorId, PlanId, SceneId, SchemaVersionStr
from app.domain.motion import MotionStyle
from app.domain.scene import SceneDefinition

PLAN_SCHEMA_VERSION = "1.0.0"
MAX_PLAN_ACTIONS = 24
MAX_PLAN_ACTORS = 2

type HandName = Literal["left", "right"]
type EffectorName = Literal["hand_l", "hand_r"]

_TIME_EPSILON = 1e-6


def hand_effector(hand: HandName) -> EffectorName:
    return "hand_r" if hand == "right" else "hand_l"


class PlanActionBase(DomainModel):
    """Fields shared by every planned action.

    ``target_ref`` values on subtypes are stable scene references: an actor id
    (``actor_x``), a scene object id (``chair_1``), or a namespaced anchor
    reference (``chair_1.seat``). ``starts_after`` expresses ordering edges in
    the action graph; an empty tuple means the action may start at time zero.
    """

    id: ActionId
    actor_id: ActorId
    starts_after: tuple[ActionId, ...] = ()
    duration: float = Field(default=1.0, gt=0.0, le=60.0)


class IdleAction(PlanActionBase):
    type: Literal["idle"] = "idle"


class ShiftWeightAction(PlanActionBase):
    type: Literal["shift_weight"] = "shift_weight"
    amount: float = Field(default=0.5, ge=-1.0, le=1.0)


class LocomoteAction(PlanActionBase):
    type: Literal["locomote"] = "locomote"
    duration: float = Field(default=2.0, gt=0.0, le=60.0)
    target_ref: str = Field(min_length=1)
    gait: Literal["walk", "brisk"] = "walk"
    stop_distance: float = Field(default=0.4, ge=0.0, le=5.0)


class ApproachAction(PlanActionBase):
    type: Literal["approach"] = "approach"
    duration: float = Field(default=2.0, gt=0.0, le=60.0)
    target_ref: str = Field(min_length=1)
    stop_distance: float = Field(default=0.9, ge=0.2, le=5.0)


class RetreatAction(PlanActionBase):
    type: Literal["retreat"] = "retreat"
    target_ref: str = Field(min_length=1)
    distance: float = Field(default=1.0, gt=0.0, le=10.0)


class TurnAction(PlanActionBase):
    type: Literal["turn"] = "turn"
    duration: float = Field(default=0.6, gt=0.0, le=60.0)
    target_ref: str | None = None
    facing: Literal["left", "right"] | None = None

    @model_validator(mode="after")
    def _check_goal(self) -> TurnAction:
        if self.target_ref is None and self.facing is None:
            raise ValueError("turn requires target_ref or facing")
        return self


class LookAtAction(PlanActionBase):
    type: Literal["look_at"] = "look_at"
    target_ref: str = Field(min_length=1)
    posture: Literal["speaking", "listening"] | None = None


class ReachAction(PlanActionBase):
    type: Literal["reach"] = "reach"
    target_ref: str = Field(min_length=1)
    hand: HandName = "right"


class PointAction(PlanActionBase):
    type: Literal["point"] = "point"
    target_ref: str = Field(min_length=1)
    hand: HandName = "right"


class GraspAction(PlanActionBase):
    type: Literal["grasp"] = "grasp"
    target_ref: str = Field(min_length=1)
    hand: HandName = "right"


class ReleaseAction(PlanActionBase):
    type: Literal["release"] = "release"
    hand: HandName = "right"


class WaveAction(PlanActionBase):
    type: Literal["wave"] = "wave"
    duration: float = Field(default=1.2, gt=0.0, le=60.0)
    hand: HandName = "right"
    amplitude: float = Field(default=0.5, ge=0.0, le=1.0)
    repetitions: int = Field(default=2, ge=1, le=12)


class SitAction(PlanActionBase):
    type: Literal["sit"] = "sit"
    target_ref: str = Field(min_length=1, description="Anchor reference with a sit affordance.")


class RiseAction(PlanActionBase):
    type: Literal["rise"] = "rise"


class CrouchAction(PlanActionBase):
    type: Literal["crouch"] = "crouch"
    amount: float = Field(default=0.6, ge=0.0, le=1.0)


class KneelAction(PlanActionBase):
    type: Literal["kneel"] = "kneel"
    amount: float = Field(default=0.8, ge=0.0, le=1.0)


class LeanAction(PlanActionBase):
    type: Literal["lean"] = "lean"
    amount: float = Field(default=0.5, ge=-1.0, le=1.0)


class HandshakeAction(PlanActionBase):
    """Two-actor handshake owned by the initiating actor (plan.md §9.4)."""

    type: Literal["handshake"] = "handshake"
    duration: float = Field(default=2.4, gt=0.0, le=60.0)
    partner_id: ActorId
    hand: HandName = "right"
    oscillations: int = Field(default=2, ge=1, le=4)


type PlannedAction = Annotated[
    IdleAction
    | ShiftWeightAction
    | LocomoteAction
    | ApproachAction
    | RetreatAction
    | TurnAction
    | LookAtAction
    | ReachAction
    | PointAction
    | GraspAction
    | ReleaseAction
    | WaveAction
    | SitAction
    | RiseAction
    | CrouchAction
    | KneelAction
    | LeanAction
    | HandshakeAction,
    Field(discriminator="type"),
]

SUPPORTED_ACTION_TYPES: tuple[str, ...] = (
    "idle",
    "shift_weight",
    "locomote",
    "approach",
    "retreat",
    "turn",
    "look_at",
    "reach",
    "point",
    "grasp",
    "release",
    "wave",
    "sit",
    "rise",
    "crouch",
    "kneel",
    "lean",
    "handshake",
)

_ACTION_CATALOG: tuple[tuple[str, str], ...] = (
    ("idle", "stand in place; use for waiting beats"),
    ("shift_weight", "small weight shift; amount -1..1"),
    ("locomote", "walk to target_ref, stopping stop_distance away"),
    ("approach", "walk toward target_ref (often the other actor), stopping at stop_distance"),
    ("retreat", "step away from target_ref by distance"),
    ("turn", "rotate to face target_ref or a facing side"),
    ("look_at", "aim gaze at target_ref; optional posture speaking|listening"),
    ("reach", "extend hand toward target_ref"),
    ("point", "point hand at target_ref"),
    ("grasp", "reach and grasp target_ref (needs a grasp affordance)"),
    ("release", "release the current grasp of hand"),
    ("wave", "wave hand; amplitude 0..1 and repetitions"),
    ("sit", "sit down on target_ref anchor (needs a sit affordance)"),
    ("rise", "stand up from sitting"),
    ("crouch", "lower into a crouch by amount"),
    ("kneel", "kneel by amount"),
    ("lean", "lean torso by amount -1..1"),
    ("handshake", "shake hands with partner_id using hand; both actors must be adjacent"),
)


def action_catalog_text() -> str:
    """Concise supported-action catalog for planner prompts (plan.md §8.2)."""
    return "\n".join(f"- {name}: {description}" for name, description in _ACTION_CATALOG)


class SyncConstraint(DomainModel):
    """Cross-lane timing constraint on two or more actions (plan.md §9.1)."""

    kind: Literal["start_together", "finish_together", "meet_at_contact"]
    action_ids: tuple[ActionId, ...] = Field(min_length=2, max_length=4)
    contact_id: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]*$")

    @model_validator(mode="after")
    def _check_contact(self) -> SyncConstraint:
        if self.kind == "meet_at_contact" and self.contact_id is None:
            raise ValueError("meet_at_contact requires contact_id")
        return self


class ContactDefinition(DomainModel):
    """An intentional contact with one hard reference side (specs §15.3).

    The reference side defines the contact point for the hold interval; the
    follower side is solved toward it. Never make both sides hard.
    """

    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    kind: Literal["hand_to_hand", "hand_to_object"]
    reference_actor_id: ActorId
    reference_hand: HandName = "right"
    follower_actor_id: ActorId | None = None
    follower_hand: HandName | None = None
    target_ref: str | None = None
    position_tolerance: float = Field(default=0.05, gt=0.0, le=0.5)
    orientation_tolerance_deg: float = Field(default=15.0, gt=0.0, le=90.0)

    @model_validator(mode="after")
    def _check_sides(self) -> ContactDefinition:
        if self.kind == "hand_to_hand":
            if self.follower_actor_id is None or self.follower_hand is None:
                raise ValueError("hand_to_hand contact requires follower actor and hand")
            if self.follower_actor_id == self.reference_actor_id:
                raise ValueError("contact reference and follower must be different actors")
        if self.kind == "hand_to_object" and self.target_ref is None:
            raise ValueError("hand_to_object contact requires target_ref")
        return self


class PlanWarning(DomainModel):
    """Model- or validator-reported uncertainty attached to the plan."""

    code: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1)
    action_id: ActionId | None = None


class MotionPlanBody(DomainModel):
    """Fields shared between the LLM draft and the persisted plan."""

    summary: str = Field(min_length=1)
    actions: tuple[PlannedAction, ...] = Field(min_length=1, max_length=MAX_PLAN_ACTIONS)
    sync: tuple[SyncConstraint, ...] = ()
    contacts: tuple[ContactDefinition, ...] = ()
    style: MotionStyle = MotionStyle()
    warnings: tuple[PlanWarning, ...] = ()


class MotionPlanDraft(MotionPlanBody):
    """Exactly what the planner model returns. No identity fields: the
    application mints ids so a model can never choose or reuse a stable id."""


class MotionPlan(MotionPlanBody):
    schema_version: SchemaVersionStr = PLAN_SCHEMA_VERSION
    id: PlanId
    scene_id: SceneId
    prompt: str = ""
    created_at: str = ""


# --- Actor capability summaries (plan.md §8.2) -------------------------------


class ActorCapabilitySummary(DomainModel):
    """Compact per-actor rig capability digest sent to the planner."""

    actor_id: ActorId
    display_name: str
    character_id: str
    effectors: tuple[str, ...]
    reach_hand_l: float
    reach_hand_r: float
    dominant_hand: HandName = "right"


def _arm_reach(character: CharacterDefinition, side: Literal["l", "r"]) -> float:
    lengths = {bone.id: bone.length for bone in character.rig.bones}
    reach = (
        lengths.get(f"upper_arm_{side}", 0.0)
        + lengths.get(f"forearm_{side}", 0.0)
        + lengths.get(f"hand_{side}", 0.0)
    )
    return round(reach if reach > 0.0 else 1.0, 4)


def build_actor_capabilities(
    scene: SceneDefinition,
    characters: dict[str, CharacterDefinition],
) -> tuple[ActorCapabilitySummary, ...]:
    summaries: list[ActorCapabilitySummary] = []
    for actor in sorted(scene.actors, key=lambda item: item.id):
        character = characters.get(actor.character_id)
        bone_ids = {bone.id for bone in character.rig.bones} if character is not None else set()
        effectors = tuple(
            effector
            for effector in ("hand_l", "hand_r", "foot_l", "foot_r", "head")
            if not bone_ids or effector in bone_ids
        )
        summaries.append(
            ActorCapabilitySummary(
                actor_id=actor.id,
                display_name=actor.display_name,
                character_id=actor.character_id,
                effectors=effectors,
                reach_hand_l=_arm_reach(character, "l") if character is not None else 1.0,
                reach_hand_r=_arm_reach(character, "r") if character is not None else 1.0,
            )
        )
    return tuple(summaries)


# --- Deterministic scheduling (plan.md §9.1) ---------------------------------


@dataclass(frozen=True, slots=True)
class ScheduledAction:
    action: PlannedAction
    start: float
    end: float


@dataclass(frozen=True, slots=True)
class PlanSchedule:
    actions: tuple[ScheduledAction, ...]
    duration: float
    contact_times: dict[str, float]
    issues: tuple[ValidationIssue, ...]
    warnings: tuple[PlanWarning, ...]


_LEG_ACTION_TYPES = frozenset(
    {"locomote", "approach", "retreat", "sit", "rise", "crouch", "kneel", "turn"}
)
_TORSO_ACTION_TYPES = frozenset({"lean", "shift_weight"})


def action_resources(action: PlannedAction) -> tuple[tuple[str, str], ...]:
    """(actor_id, resource) pairs an action occupies while it runs."""
    if action.type in _LEG_ACTION_TYPES:
        return ((action.actor_id, "legs"),)
    if isinstance(
        action, ReachAction | PointAction | GraspAction | WaveAction | ReleaseAction
    ):
        return ((action.actor_id, hand_effector(action.hand)),)
    if action.type == "look_at":
        return ((action.actor_id, "head"),)
    if action.type in _TORSO_ACTION_TYPES:
        return ((action.actor_id, "torso"),)
    if isinstance(action, HandshakeAction):
        return (
            (action.actor_id, hand_effector(action.hand)),
            (action.partner_id, hand_effector(action.hand)),
        )
    return ()


def _topological_order(
    plan: MotionPlanBody,
) -> tuple[tuple[PlannedAction, ...], list[ValidationIssue]]:
    issues: list[ValidationIssue] = []
    by_id: dict[str, PlannedAction] = {}
    for index, action in enumerate(plan.actions):
        if action.id in by_id:
            issues.append(
                ValidationIssue(
                    "PLAN_DUPLICATE_ACTION_ID",
                    f"action id {action.id!r} is defined more than once",
                    f"actions[{index}].id",
                )
            )
        by_id[action.id] = action

    for index, action in enumerate(plan.actions):
        for dep in action.starts_after:
            if dep not in by_id:
                issues.append(
                    ValidationIssue(
                        "PLAN_UNKNOWN_ACTION_REF",
                        f"action {action.id!r} starts after unknown action {dep!r}",
                        f"actions[{index}].starts_after",
                    )
                )
            elif dep == action.id:
                issues.append(
                    ValidationIssue(
                        "PLAN_SELF_DEPENDENCY",
                        f"action {action.id!r} cannot start after itself",
                        f"actions[{index}].starts_after",
                    )
                )

    # Kahn's algorithm with stable plan order so scheduling is deterministic.
    remaining = {action.id for action in plan.actions}
    ordered: list[PlannedAction] = []
    while remaining:
        progressed = False
        for action in plan.actions:
            if action.id not in remaining:
                continue
            deps = [dep for dep in action.starts_after if dep in remaining and dep != action.id]
            if not deps:
                ordered.append(action)
                remaining.discard(action.id)
                progressed = True
        if not progressed:
            cycle_ids = ", ".join(sorted(remaining))
            issues.append(
                ValidationIssue(
                    "PLAN_CYCLE",
                    f"action graph contains a cycle involving: {cycle_ids}",
                    "actions",
                )
            )
            break
    return tuple(ordered), issues


def schedule_plan(plan: MotionPlanBody) -> PlanSchedule:
    """Resolve the action graph into absolute per-lane time ranges."""
    ordered, issues = _topological_order(plan)
    warnings: list[PlanWarning] = []
    contact_times: dict[str, float] = {}
    if any(issue.code == "PLAN_CYCLE" for issue in issues):
        return PlanSchedule((), 0.0, {}, tuple(issues), ())

    by_id = {action.id: action for action in plan.actions}
    extra_delay: dict[str, float] = {action.id: 0.0 for action in plan.actions}
    starts: dict[str, float] = {}
    ends: dict[str, float] = {}

    def recompute() -> None:
        for action in ordered:
            dep_end = max(
                (ends[dep] for dep in action.starts_after if dep in ends),
                default=0.0,
            )
            starts[action.id] = round(max(dep_end, extra_delay[action.id]), 4)
            ends[action.id] = round(starts[action.id] + action.duration, 4)

    recompute()
    for _ in range(len(plan.sync) * 2 + 1):
        changed = False
        for constraint in plan.sync:
            members = [action_id for action_id in constraint.action_ids if action_id in by_id]
            if len(members) < 2:
                continue
            if constraint.kind == "start_together":
                target = max(starts[action_id] for action_id in members)
                for action_id in members:
                    if starts[action_id] < target - _TIME_EPSILON:
                        extra_delay[action_id] = target
                        changed = True
            else:  # finish_together and meet_at_contact align ends.
                target = max(ends[action_id] for action_id in members)
                for action_id in members:
                    desired_start = round(target - by_id[action_id].duration, 4)
                    if abs(starts[action_id] - desired_start) > _TIME_EPSILON and desired_start > (
                        starts[action_id] - _TIME_EPSILON
                    ):
                        extra_delay[action_id] = desired_start
                        changed = True
                if constraint.kind == "meet_at_contact" and constraint.contact_id is not None:
                    contact_times[constraint.contact_id] = target
        if not changed:
            break
        recompute()

    for constraint in plan.sync:
        members = [action_id for action_id in constraint.action_ids if action_id in by_id]
        if len(members) < 2:
            issues.append(
                ValidationIssue(
                    "PLAN_SYNC_UNKNOWN_ACTION",
                    f"sync constraint references unknown actions: {list(constraint.action_ids)}",
                    "sync",
                )
            )
            continue
        values = (
            [starts[action_id] for action_id in members]
            if constraint.kind == "start_together"
            else [ends[action_id] for action_id in members]
        )
        if max(values) - min(values) > 1e-3:
            warnings.append(
                PlanWarning(
                    code="SYNC_UNSATISFIED",
                    message=(
                        f"{constraint.kind} constraint on {list(members)} could not be "
                        "fully satisfied because of ordering dependencies"
                    ),
                )
            )

    scheduled = tuple(
        ScheduledAction(action=action, start=starts[action.id], end=ends[action.id])
        for action in ordered
    )

    # Actor resource exclusivity: two overlapping actions must not use the
    # same limb of the same actor (plan.md §8.3 and §9.1).
    for left_index, left in enumerate(scheduled):
        left_resources = set(action_resources(left.action))
        if not left_resources:
            continue
        for right in scheduled[left_index + 1 :]:
            overlap = min(left.end, right.end) - max(left.start, right.start)
            if overlap <= 1e-3:
                continue
            shared = left_resources.intersection(action_resources(right.action))
            if shared:
                resources = ", ".join(sorted(f"{actor}:{res}" for actor, res in shared))
                issues.append(
                    ValidationIssue(
                        "PLAN_RESOURCE_CONFLICT",
                        f"actions {left.action.id!r} and {right.action.id!r} overlap in "
                        f"time and both use {resources}",
                        "actions",
                    )
                )

    duration = round(max((item.end for item in scheduled), default=0.0), 4)
    return PlanSchedule(scheduled, duration, contact_times, tuple(issues), tuple(warnings))


# --- Patch schema for corrections (plan.md §8.6) -----------------------------


class PatchSetParameters(DomainModel):
    """Update editable scalar parameters of one existing action."""

    op: Literal["set_parameters"] = "set_parameters"
    action_id: ActionId
    duration: float | None = Field(default=None, gt=0.0, le=60.0)
    target_ref: str | None = None
    hand: HandName | None = None
    amplitude: float | None = Field(default=None, ge=0.0, le=1.0)
    repetitions: int | None = Field(default=None, ge=1, le=12)
    stop_distance: float | None = Field(default=None, ge=0.0, le=5.0)
    amount: float | None = Field(default=None, ge=-1.0, le=1.0)


class PatchReplaceAction(DomainModel):
    op: Literal["replace_action"] = "replace_action"
    action_id: ActionId
    action: PlannedAction


class PatchInsertAction(DomainModel):
    op: Literal["insert_action"] = "insert_action"
    after_action_id: ActionId | None = None
    action: PlannedAction


class PatchRemoveAction(DomainModel):
    op: Literal["remove_action"] = "remove_action"
    action_id: ActionId


class PatchSetStyle(DomainModel):
    op: Literal["set_style"] = "set_style"
    style: MotionStyle


type PatchOperation = Annotated[
    PatchSetParameters | PatchReplaceAction | PatchInsertAction | PatchRemoveAction | PatchSetStyle,
    Field(discriminator="op"),
]


class MotionPlanPatch(DomainModel):
    """A correction against stable action ids, never a new unrelated plan."""

    summary: str = Field(min_length=1)
    operations: tuple[PatchOperation, ...] = Field(min_length=1, max_length=8)
    warnings: tuple[PlanWarning, ...] = ()


@dataclass(frozen=True, slots=True)
class PatchApplication:
    plan: MotionPlan | None
    issues: tuple[ValidationIssue, ...]
    diff: tuple[str, ...]


def describe_patch_operation(operation: PatchOperation) -> str:
    if isinstance(operation, PatchSetParameters):
        fields = {
            name: value
            for name, value in operation.model_dump(mode="json").items()
            if name not in {"op", "action_id"} and value is not None
        }
        parts = ", ".join(f"{name}={value}" for name, value in sorted(fields.items()))
        return f"set {parts or 'nothing'} on action {operation.action_id}"
    if isinstance(operation, PatchReplaceAction):
        return f"replace action {operation.action_id} with a {operation.action.type} action"
    if isinstance(operation, PatchInsertAction):
        anchor = f"after {operation.after_action_id}" if operation.after_action_id else "at start"
        return f"insert {operation.action.type} action {operation.action.id} {anchor}"
    if isinstance(operation, PatchRemoveAction):
        return f"remove action {operation.action_id}"
    return "update plan style"


def apply_plan_patch(plan: MotionPlan, patch: MotionPlanPatch) -> PatchApplication:
    """Deterministically apply a validated patch to a plan.

    Returns the patched plan or the issues that make the patch inapplicable.
    The patched plan is re-validated structurally so a patch can never produce
    an out-of-contract document.
    """
    issues: list[ValidationIssue] = []
    diff: list[str] = []
    actions: list[PlannedAction] = list(plan.actions)
    style = plan.style
    ids = {action.id for action in actions}

    for index, operation in enumerate(patch.operations):
        path = f"operations[{index}]"
        if isinstance(operation, PatchSetParameters):
            position = next(
                (i for i, action in enumerate(actions) if action.id == operation.action_id), None
            )
            if position is None:
                issues.append(
                    ValidationIssue(
                        "PATCH_UNKNOWN_ACTION",
                        f"patch references unknown action {operation.action_id!r}",
                        f"{path}.action_id",
                    )
                )
                continue
            target = actions[position]
            updates = {
                name: value
                for name, value in operation.model_dump(mode="python").items()
                if name not in {"op", "action_id"} and value is not None
            }
            model_fields = type(target).model_fields
            unknown = sorted(name for name in updates if name not in model_fields)
            if unknown:
                issues.append(
                    ValidationIssue(
                        "PATCH_INVALID_FIELD",
                        f"action {target.id!r} of type {target.type!r} has no field(s): "
                        f"{', '.join(unknown)}",
                        path,
                    )
                )
                continue
            dumped = target.model_dump(mode="python")
            dumped.update(updates)
            actions[position] = type(target).model_validate(dumped)
        elif isinstance(operation, PatchReplaceAction):
            if operation.action.id != operation.action_id:
                issues.append(
                    ValidationIssue(
                        "PATCH_ID_MISMATCH",
                        "replacement action must keep the replaced action id",
                        f"{path}.action.id",
                    )
                )
                continue
            position = next(
                (i for i, action in enumerate(actions) if action.id == operation.action_id), None
            )
            if position is None:
                issues.append(
                    ValidationIssue(
                        "PATCH_UNKNOWN_ACTION",
                        f"patch references unknown action {operation.action_id!r}",
                        f"{path}.action_id",
                    )
                )
                continue
            actions[position] = operation.action
        elif isinstance(operation, PatchInsertAction):
            if operation.action.id in ids:
                issues.append(
                    ValidationIssue(
                        "PATCH_DUPLICATE_ACTION_ID",
                        f"inserted action id {operation.action.id!r} already exists",
                        f"{path}.action.id",
                    )
                )
                continue
            if operation.after_action_id is None:
                actions.insert(0, operation.action)
            else:
                position = next(
                    (
                        i
                        for i, action in enumerate(actions)
                        if action.id == operation.after_action_id
                    ),
                    None,
                )
                if position is None:
                    issues.append(
                        ValidationIssue(
                            "PATCH_UNKNOWN_ACTION",
                            f"patch inserts after unknown action {operation.after_action_id!r}",
                            f"{path}.after_action_id",
                        )
                    )
                    continue
                actions.insert(position + 1, operation.action)
            ids.add(operation.action.id)
        elif isinstance(operation, PatchRemoveAction):
            position = next(
                (i for i, action in enumerate(actions) if action.id == operation.action_id), None
            )
            if position is None:
                issues.append(
                    ValidationIssue(
                        "PATCH_UNKNOWN_ACTION",
                        f"patch removes unknown action {operation.action_id!r}",
                        f"{path}.action_id",
                    )
                )
                continue
            removed = actions.pop(position)
            actions = [
                action.model_copy(
                    update={
                        "starts_after": tuple(
                            dep for dep in action.starts_after if dep != removed.id
                        )
                    }
                )
                for action in actions
            ]
            ids.discard(removed.id)
        else:
            style = operation.style
        diff.append(describe_patch_operation(operation))

    if issues:
        return PatchApplication(plan=None, issues=tuple(issues), diff=tuple(diff))
    if not actions:
        empty = ValidationIssue(
            "PATCH_EMPTY_PLAN", "patch would remove every action", "operations"
        )
        return PatchApplication(plan=None, issues=(empty,), diff=tuple(diff))
    patched = MotionPlan.model_validate(
        {
            **plan.model_dump(mode="python"),
            "actions": tuple(actions),
            "style": style,
        }
    )
    return PatchApplication(plan=patched, issues=(), diff=tuple(diff))


# --- Canned fixtures (plan.md §10) -------------------------------------------

# Deterministic canned drafts so the workflow is testable and demonstrable
# without a live model. They target the shared room-scene fixture ids.
CANNED_MOTION_PLAN_DRAFT = MotionPlanDraft(
    summary="Mira walks to the chair, sits down, and waves.",
    actions=(
        LocomoteAction(
            id="a1", actor_id="actor_mira", target_ref="chair_main.seat", duration=2.4
        ),
        SitAction(id="a2", actor_id="actor_mira", target_ref="chair_main.seat", duration=1.2,
                  starts_after=("a1",)),
        WaveAction(id="a3", actor_id="actor_mira", hand="right", duration=1.6, repetitions=2,
                   amplitude=0.45, starts_after=("a2",)),
    ),
    style=MotionStyle(energy=0.35, confidence=0.65, exaggeration=0.2, tempo=0.9),
)

CANNED_HANDSHAKE_PLAN_DRAFT = MotionPlanDraft(
    summary="Mira approaches Jon, shakes his right hand, then both look toward the door.",
    actions=(
        ApproachAction(
            id="a1", actor_id="actor_mira", target_ref="actor_jon", duration=2.2,
            stop_distance=0.9,
        ),
        TurnAction(id="a2", actor_id="actor_jon", target_ref="actor_mira", duration=0.6),
        HandshakeAction(
            id="a3", actor_id="actor_mira", partner_id="actor_jon", hand="right",
            duration=2.4, oscillations=2, starts_after=("a1", "a2"),
        ),
        LookAtAction(
            id="a4", actor_id="actor_mira", target_ref="door_main", duration=1.0,
            starts_after=("a3",),
        ),
        LookAtAction(
            id="a5", actor_id="actor_jon", target_ref="door_main", duration=1.0,
            starts_after=("a3",),
        ),
    ),
    sync=(
        SyncConstraint(kind="start_together", action_ids=("a4", "a5")),
        SyncConstraint(kind="meet_at_contact", action_ids=("a1", "a2"), contact_id="shake"),
    ),
    contacts=(
        ContactDefinition(
            id="shake",
            kind="hand_to_hand",
            reference_actor_id="actor_mira",
            reference_hand="right",
            follower_actor_id="actor_jon",
            follower_hand="right",
        ),
    ),
    style=MotionStyle(energy=0.4, confidence=0.7),
)
