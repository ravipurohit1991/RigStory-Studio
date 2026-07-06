from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain.character import CharacterDefinition
from app.domain.clip import ClipMarker
from app.domain.motion import MotionCompileResult
from app.domain.motion_plan import (
    CANNED_HANDSHAKE_PLAN_DRAFT,
    CANNED_MOTION_PLAN_DRAFT,
    MotionPlan,
    MotionPlanDraft,
    MotionPlanPatch,
    PatchInsertAction,
    WaveAction,
    apply_plan_patch,
    schedule_plan,
)
from app.domain.plan_compiler import (
    HARD_OVERLAP_DISTANCE,
    MIN_ACTOR_SPACING,
    compile_motion_plan,
)
from app.domain.project import load_project_document
from app.domain.scene import SceneDefinition
from tests.domain.test_scene_phase6 import room_scene
from tests.sample_paths import load_sample


def _characters() -> dict[str, CharacterDefinition]:
    project = load_project_document(load_sample("projects/biped-demo.rigstory.json")).document
    return {character.id: character for character in project.characters}


def _plan(draft: MotionPlanDraft, prompt: str = "test prompt") -> MotionPlan:
    return MotionPlan.model_validate(
        {
            **draft.model_dump(mode="python"),
            "id": "plan_test",
            "scene_id": "scene_room",
            "prompt": prompt,
        }
    )


def _compile(plan: MotionPlan, clip_id: str = "clip_plan_test") -> MotionCompileResult:
    return compile_motion_plan(
        scene=room_scene(),
        characters=_characters(),
        plan=plan,
        clip_id=clip_id,
    )


def test_walk_sit_wave_plan_compiles_expected_graph_and_clip() -> None:
    plan = _plan(CANNED_MOTION_PLAN_DRAFT, prompt="Walk to the chair, sit, and wave")
    schedule = schedule_plan(plan)
    ordered = [item.action.id for item in sorted(schedule.actions, key=lambda i: i.start)]
    assert ordered == ["a1", "a2", "a3"]

    result = _compile(plan)
    repeat = _compile(plan)
    assert result == repeat
    assert result.clip.source_plan_id == "plan_test"
    assert result.clip.engine_version == result.engine_version
    assert {track.type for track in result.clip.tracks} >= {
        "root_translation",
        "bone_rotation",
    }
    assert any(marker.name == "a2_seated" for marker in result.clip.markers)
    assert result.report.metrics.max_joint_limit_violation_deg == 0.0
    assert result.report.metrics.max_foot_slide == 0.0


def test_handshake_compiles_contact_sync_and_spacing() -> None:
    plan = _plan(
        CANNED_HANDSHAKE_PLAN_DRAFT,
        prompt="Mira approaches Jon, shakes his right hand, then they look toward the door.",
    )
    result = _compile(plan, clip_id="clip_handshake")
    repeat = _compile(plan, clip_id="clip_handshake")
    assert result == repeat

    marker_names = {marker.name for marker in result.clip.markers}
    assert {"shake_contact_start", "shake_contact_end", "a3_sync"} <= marker_names
    contact_start = next(
        marker for marker in result.clip.markers if marker.name == "shake_contact_start"
    )
    contact_end = next(
        marker for marker in result.clip.markers if marker.name == "shake_contact_end"
    )
    assert contact_start.kind == "contact"
    assert contact_end.time > contact_start.time

    # Approach without overlap: no penetration frames and feet stay planted.
    assert result.report.metrics.penetration_frames == 0
    assert result.report.metrics.max_foot_slide == 0.0
    # Contact held within tolerance: both IK solves reached the shared point.
    contact = plan.contacts[0]
    assert result.report.metrics.max_target_error <= contact.position_tolerance

    # Both actors have editable lanes in the same clip.
    actor_ids = {track.actor_id for track in result.clip.tracks}
    assert actor_ids == {"actor_mira", "actor_jon"}

    # The initiator stops outside the personal-space envelope of the partner.
    mira_root = next(
        track
        for track in result.clip.tracks
        if track.type == "root_translation" and track.actor_id == "actor_mira"
    )
    jon_root = next(
        track
        for track in result.clip.tracks
        if track.type == "root_translation" and track.actor_id == "actor_jon"
    )
    final_mira = mira_root.keyframes[-1].value
    final_jon = jon_root.keyframes[-1].value
    distance = ((final_mira[0] - final_jon[0]) ** 2 + (final_mira[1] - final_jon[1]) ** 2) ** 0.5
    assert distance >= MIN_ACTOR_SPACING - 1e-6
    assert distance >= HARD_OVERLAP_DISTANCE


def test_editing_unrelated_gesture_keeps_handshake_markers_stable() -> None:
    plan = _plan(CANNED_HANDSHAKE_PLAN_DRAFT)
    baseline = _compile(plan, clip_id="clip_handshake")

    patch = MotionPlanPatch(
        summary="Jon waves after looking at the door",
        operations=(
            PatchInsertAction(
                after_action_id="a5",
                action=WaveAction(
                    id="a6",
                    actor_id="actor_jon",
                    hand="left",
                    duration=1.0,
                    starts_after=("a5",),
                ),
            ),
        ),
    )
    application = apply_plan_patch(plan, patch)
    assert application.plan is not None
    patched = _compile(application.plan, clip_id="clip_handshake")

    def marker_time(result_markers: tuple[ClipMarker, ...], name: str) -> float:
        return next(marker.time for marker in result_markers if marker.name == name)

    for name in ("shake_contact_start", "shake_contact_end", "a3_sync"):
        assert marker_time(patched.clip.markers, name) == pytest.approx(
            marker_time(baseline.clip.markers, name)
        )
    assert patched.clip.duration > baseline.clip.duration


def test_shared_gaze_and_posture_markers() -> None:
    plan = _plan(CANNED_HANDSHAKE_PLAN_DRAFT)
    result = _compile(plan)
    head_tracks = [
        track
        for track in result.clip.tracks
        if track.type == "bone_rotation" and track.bone_id == "head"
    ]
    assert {track.actor_id for track in head_tracks} == {"actor_mira", "actor_jon"}
    for track in head_tracks:
        assert len(track.keyframes) >= 2


def test_more_than_two_actors_is_rejected_at_the_scene_schema() -> None:
    scene = room_scene()
    third = scene.actors[0].model_copy(update={"id": "actor_third"})
    with pytest.raises(ValidationError):
        SceneDefinition.model_validate(
            {
                **scene.model_dump(mode="json"),
                "actors": [actor.model_dump(mode="json") for actor in (*scene.actors, third)],
            }
        )
