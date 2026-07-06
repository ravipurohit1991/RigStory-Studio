from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain.motion_plan import (
    CANNED_HANDSHAKE_PLAN_DRAFT,
    CANNED_MOTION_PLAN_DRAFT,
    HandshakeAction,
    LookAtAction,
    MotionPlan,
    MotionPlanDraft,
    MotionPlanPatch,
    PatchRemoveAction,
    PatchSetParameters,
    ReachAction,
    SitAction,
    SyncConstraint,
    WaveAction,
    apply_plan_patch,
    schedule_plan,
)
from app.domain.motion_plan_validation import validate_motion_plan
from app.domain.project import load_project_document
from app.domain.scene_snapshot import SceneSnapshot, build_scene_snapshot
from tests.domain.test_scene_phase6 import room_scene
from tests.sample_paths import load_sample


def _snapshot() -> SceneSnapshot:
    project = load_project_document(load_sample("projects/biped-demo.rigstory.json")).document
    characters = {character.id: character for character in project.characters}
    return build_scene_snapshot(room_scene(), characters=characters)


def _plan(draft: MotionPlanDraft, prompt: str = "") -> MotionPlan:
    return MotionPlan.model_validate(
        {
            **draft.model_dump(mode="python"),
            "id": "plan_test",
            "scene_id": "scene_room",
            "prompt": prompt,
        }
    )


def test_plan_schema_rejects_invented_fields_and_bad_ids() -> None:
    base = CANNED_MOTION_PLAN_DRAFT.model_dump(mode="json")
    with pytest.raises(ValidationError):
        MotionPlanDraft.model_validate({**base, "frames": []})
    bad_action = dict(base["actions"][0])
    bad_action["id"] = "Not A Slug"
    with pytest.raises(ValidationError):
        MotionPlanDraft.model_validate({**base, "actions": [bad_action]})
    with pytest.raises(ValidationError):
        MotionPlanDraft.model_validate({**base, "actions": []})


def test_schedule_resolves_ordering_and_sync_constraints() -> None:
    draft = CANNED_HANDSHAKE_PLAN_DRAFT
    schedule = schedule_plan(draft)
    assert schedule.issues == ()
    by_id = {item.action.id: item for item in schedule.actions}
    # a3 starts only after both preparations are done.
    assert by_id["a3"].start == pytest.approx(max(by_id["a1"].end, by_id["a2"].end))
    # start_together aligns the two look_at actions.
    assert by_id["a4"].start == pytest.approx(by_id["a5"].start)
    # meet_at_contact aligns the approach and turn ends and records the time.
    assert by_id["a1"].end == pytest.approx(by_id["a2"].end)
    assert schedule.contact_times["shake"] == pytest.approx(by_id["a1"].end)


def test_schedule_detects_cycles_and_limb_conflicts() -> None:
    cycle = MotionPlanDraft(
        summary="cycle",
        actions=(
            WaveAction(id="a1", actor_id="actor_mira", starts_after=("a2",)),
            WaveAction(id="a2", actor_id="actor_mira", starts_after=("a1",)),
        ),
    )
    assert "PLAN_CYCLE" in {issue.code for issue in schedule_plan(cycle).issues}

    conflict = MotionPlanDraft(
        summary="conflict",
        actions=(
            WaveAction(id="a1", actor_id="actor_mira", hand="right", duration=2.0),
            ReachAction(
                id="a2",
                actor_id="actor_mira",
                hand="right",
                target_ref="door_main.handle",
                duration=2.0,
            ),
        ),
    )
    assert "PLAN_RESOURCE_CONFLICT" in {issue.code for issue in schedule_plan(conflict).issues}


def test_validate_rejects_unknown_references_instead_of_fabricating() -> None:
    snapshot = _snapshot()
    unknown_target = MotionPlanDraft(
        summary="walk to a sofa that does not exist",
        actions=(SitAction(id="a1", actor_id="actor_mira", target_ref="sofa_1.seat"),),
    )
    result = validate_motion_plan(unknown_target, snapshot)
    assert "PLAN_UNKNOWN_TARGET" in {issue.code for issue in result.errors}

    unknown_actor = MotionPlanDraft(
        summary="unknown actor",
        actions=(WaveAction(id="a1", actor_id="actor_ghost"),),
    )
    result = validate_motion_plan(unknown_actor, snapshot)
    assert "PLAN_UNKNOWN_ACTOR" in {issue.code for issue in result.errors}


def test_validate_checks_affordances_and_reachability() -> None:
    snapshot = _snapshot()
    bad_sit = MotionPlanDraft(
        summary="sit on the door handle",
        actions=(SitAction(id="a1", actor_id="actor_mira", target_ref="door_main.handle"),),
    )
    result = validate_motion_plan(bad_sit, snapshot)
    assert "PLAN_AFFORDANCE_MISMATCH" in {issue.code for issue in result.errors}

    far_reach = MotionPlanDraft(
        summary="reach the far door handle without walking",
        actions=(ReachAction(id="a1", actor_id="actor_mira", target_ref="door_main.handle"),),
    )
    result = validate_motion_plan(far_reach, snapshot)
    assert result.errors == ()
    assert "TARGET_MAY_BE_UNREACHABLE" in {warning.code for warning in result.warnings}


def test_validate_flags_two_actor_ambiguity_and_contact_feasibility() -> None:
    snapshot = _snapshot()
    plan = _plan(CANNED_HANDSHAKE_PLAN_DRAFT, prompt="She walks over and shakes his hand.")
    result = validate_motion_plan(plan, snapshot)
    assert result.errors == ()
    assert "PRONOUN_AMBIGUITY" in {warning.code for warning in result.warnings}

    named = _plan(
        CANNED_HANDSHAKE_PLAN_DRAFT,
        prompt="Mira approaches Jon and shakes his right hand.",
    )
    assert "PRONOUN_AMBIGUITY" not in {
        warning.code for warning in validate_motion_plan(named, snapshot).warnings
    }

    infeasible = MotionPlanDraft(
        summary="handshake without approaching first",
        actions=(HandshakeAction(id="a1", actor_id="actor_mira", partner_id="actor_jon"),),
    )
    result = validate_motion_plan(infeasible, snapshot)
    assert "PLAN_CONTACT_INFEASIBLE" in {issue.code for issue in result.errors}


def test_validate_enforces_actor_count_and_handedness() -> None:
    snapshot = _snapshot()
    draft = CANNED_HANDSHAKE_PLAN_DRAFT
    mismatched = draft.model_copy(
        update={
            "actions": tuple(
                action.model_copy(update={"hand": "left"})
                if isinstance(action, HandshakeAction)
                else action
                for action in draft.actions
            )
        }
    )
    result = validate_motion_plan(mismatched, snapshot)
    assert "PLAN_HANDEDNESS_MISMATCH" in {issue.code for issue in result.errors}


def test_apply_patch_changes_only_the_targeted_action() -> None:
    plan = _plan(CANNED_MOTION_PLAN_DRAFT)
    patch = MotionPlanPatch(
        summary="make the wave smaller",
        operations=(PatchSetParameters(action_id="a3", amplitude=0.2, repetitions=1),),
    )
    application = apply_plan_patch(plan, patch)
    assert application.issues == ()
    assert application.plan is not None
    patched_wave = next(action for action in application.plan.actions if action.id == "a3")
    assert isinstance(patched_wave, WaveAction)
    assert patched_wave.amplitude == 0.2
    assert patched_wave.repetitions == 1
    unchanged = [action for action in application.plan.actions if action.id != "a3"]
    original = [action for action in plan.actions if action.id != "a3"]
    assert unchanged == original
    assert application.diff == ("set amplitude=0.2, repetitions=1 on action a3",)


def test_apply_patch_rejects_unknown_ids_and_invalid_fields() -> None:
    plan = _plan(CANNED_MOTION_PLAN_DRAFT)
    unknown = MotionPlanPatch(
        summary="patch a ghost",
        operations=(PatchSetParameters(action_id="ghost", amplitude=0.2),),
    )
    application = apply_plan_patch(plan, unknown)
    assert application.plan is None
    assert "PATCH_UNKNOWN_ACTION" in {issue.code for issue in application.issues}

    invalid_field = MotionPlanPatch(
        summary="waves have no stop distance",
        operations=(PatchSetParameters(action_id="a3", stop_distance=0.5),),
    )
    application = apply_plan_patch(plan, invalid_field)
    assert application.plan is None
    assert "PATCH_INVALID_FIELD" in {issue.code for issue in application.issues}


def test_apply_patch_remove_drops_dependencies() -> None:
    plan = _plan(CANNED_MOTION_PLAN_DRAFT)
    patch = MotionPlanPatch(
        summary="drop the sit",
        operations=(PatchRemoveAction(action_id="a2"),),
    )
    application = apply_plan_patch(plan, patch)
    assert application.plan is not None
    wave = next(action for action in application.plan.actions if action.id == "a3")
    assert wave.starts_after == ()


def test_sync_constraint_requires_contact_id_for_meet_at_contact() -> None:
    with pytest.raises(ValidationError):
        SyncConstraint(kind="meet_at_contact", action_ids=("a1", "a2"))


def test_canned_plans_validate_against_room_scene() -> None:
    snapshot = _snapshot()
    for draft in (CANNED_MOTION_PLAN_DRAFT, CANNED_HANDSHAKE_PLAN_DRAFT):
        result = validate_motion_plan(draft, snapshot)
        assert result.errors == ()


def test_look_at_posture_is_typed() -> None:
    action = LookAtAction(
        id="a1", actor_id="actor_mira", target_ref="actor_jon", posture="speaking"
    )
    assert action.posture == "speaking"
    with pytest.raises(ValidationError):
        LookAtAction.model_validate(
            {"id": "a1", "actor_id": "actor_mira", "target_ref": "x", "posture": "singing"}
        )
