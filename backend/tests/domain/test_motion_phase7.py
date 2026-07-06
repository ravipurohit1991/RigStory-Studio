from __future__ import annotations

from app.domain.math2d.vec2 import Vec2
from app.domain.motion import MotionAction, compile_motion_actions, solve_two_bone_ik
from app.domain.project import load_project_document
from tests.domain.test_scene_phase6 import room_scene
from tests.sample_paths import load_sample


def _character():
    project = load_project_document(load_sample("projects/biped-demo.rigstory.json")).document
    return project.characters[0]


def test_two_bone_ik_reaches_and_clamps_deterministically() -> None:
    reachable = solve_two_bone_ik(
        start=Vec2.zero(),
        target=Vec2(0.7, 0.5),
        upper_length=0.6,
        lower_length=0.5,
        bend_direction="positive",
    )
    repeat = solve_two_bone_ik(
        start=Vec2.zero(),
        target=Vec2(0.7, 0.5),
        upper_length=0.6,
        lower_length=0.5,
        bend_direction="positive",
    )
    assert reachable == repeat
    assert reachable.reachable
    assert reachable.target_error < 1e-6

    clamped = solve_two_bone_ik(
        start=Vec2.zero(),
        target=Vec2(2.0, 0.0),
        upper_length=0.6,
        lower_length=0.5,
    )
    assert not clamped.reachable
    assert clamped.clamped
    assert clamped.target_error > 0.8


def test_compile_walk_turn_sit_wave_sequence_is_deterministic() -> None:
    scene = room_scene()
    character = _character()
    actions = (
        MotionAction(id="walk", type="locomote", target=(2.2, 0.0), duration=2.0),
        MotionAction(id="turn", type="turn", target=(6.0, 1.0), duration=0.6),
        MotionAction(id="sit", type="sit", anchor_ref="chair_main.seat", duration=1.0),
        MotionAction(id="wave", type="wave", hand="right", repetitions=2, duration=1.2, amount=0.7),
    )
    result = compile_motion_actions(
        scene=scene,
        actor_id="actor_mira",
        character=character,
        actions=actions,
        clip_id="clip_phase7_demo",
    )
    repeat = compile_motion_actions(
        scene=scene,
        actor_id="actor_mira",
        character=character,
        actions=actions,
        clip_id="clip_phase7_demo",
    )
    assert result == repeat
    assert result.clip.duration > 4.0
    assert result.report.metrics.max_foot_slide == 0.0
    assert result.report.metrics.max_joint_limit_violation_deg == 0.0
    assert {track.type for track in result.clip.tracks} >= {"root_translation", "bone_rotation"}
    assert any(marker.name == "sit_seated" for marker in result.clip.markers)
    assert "PATH_DETOUR" in {warning.code for warning in result.report.warnings}


def test_compile_reach_reports_unreachable_target() -> None:
    result = compile_motion_actions(
        scene=room_scene(),
        actor_id="actor_mira",
        character=_character(),
        actions=(MotionAction(id="reach_far", type="reach", target=(6.5, 3.0), duration=1.0),),
        clip_id="clip_reach_far",
    )
    assert result.report.status == "warning"
    assert "TARGET_UNREACHABLE_CLAMPED" in {warning.code for warning in result.report.warnings}
    assert result.report.metrics.max_target_error > 0.0
