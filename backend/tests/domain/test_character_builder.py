from __future__ import annotations

from typing import cast

from hypothesis import given, settings
from hypothesis import strategies as st

from app.domain.canonical import JsonValue, model_canonical_json
from app.domain.character import validate_character
from app.domain.character_builder import (
    PRESET_REQUESTS,
    CharacterBuilderRequest,
    CharacterProportions,
    build_procedural_character,
    combined_character_svg,
    primitive_attachment_svg,
)
from tests.sample_paths import load_sample

REQUIRED_BONE_IDS = {
    "root",
    "hips",
    "spine_lower",
    "spine_upper",
    "chest",
    "neck",
    "head",
    "eye_l",
    "eye_r",
    "clavicle_l",
    "upper_arm_l",
    "forearm_l",
    "hand_l",
    "thigh_l",
    "shin_l",
    "foot_l",
    "toe_l",
    "clavicle_r",
    "upper_arm_r",
    "forearm_r",
    "hand_r",
    "thigh_r",
    "shin_r",
    "foot_r",
    "toe_r",
}


def _fixture_requests() -> list[CharacterBuilderRequest]:
    raw = cast(
        list[JsonValue],
        load_sample("fixtures/character-builder-requests.json")["requests"],
    )
    return [CharacterBuilderRequest.model_validate(item) for item in raw]


def test_preset_fixture_file_matches_builtin_count() -> None:
    fixture_requests = _fixture_requests()

    assert len(fixture_requests) >= 10
    assert len(PRESET_REQUESTS) == len(fixture_requests)
    assert [request.name for request in PRESET_REQUESTS] == [
        request.name for request in fixture_requests
    ]


def test_diverse_request_fixtures_generate_valid_editable_characters() -> None:
    for request in _fixture_requests():
        result = build_procedural_character(request)
        character = result.character

        assert {diagnostic.severity for diagnostic in result.diagnostics} <= {
            "info",
            "warning",
        }
        assert validate_character(character) == []
        assert {bone.id for bone in character.rig.bones} == REQUIRED_BONE_IDS
        assert {constraint.id for constraint in result.constraints} == {
            "ik_arm_l",
            "ik_arm_r",
            "ik_leg_l",
            "ik_leg_r",
            "look_eyes",
            "look_head",
        }
        assert len(character.attachments) >= 25

        attachment_ids = {attachment.id for attachment in character.attachments}
        assert {"part_head", "part_torso", "part_pelvis", "part_eye_l", "part_eye_r"} <= (
            attachment_ids
        )
        if request.hair_style != "bald":
            assert {"part_hair_back", "part_hair_front"} <= attachment_ids
        if request.bottom == "skirt":
            assert "part_skirt" in attachment_ids

        bone_ids = {bone.id for bone in character.rig.bones}
        assert all(attachment.bone_id in bone_ids for attachment in character.attachments)
        assert {
            "upper_arm_l",
            "forearm_l",
            "hand_l",
            "thigh_l",
            "shin_l",
            "foot_l",
            "upper_arm_r",
            "forearm_r",
            "hand_r",
            "thigh_r",
            "shin_r",
            "foot_r",
        } <= bone_ids


def test_generated_output_is_identical_for_identical_normalized_input() -> None:
    request = PRESET_REQUESTS[0]

    first = build_procedural_character(request)
    second = build_procedural_character(request)

    assert model_canonical_json(first.character) == model_canonical_json(second.character)
    assert first.character.id == second.character.id
    assert first.character.rig.id == second.character.rig.id
    assert first.constraints == second.constraints


def test_out_of_range_proportions_are_clamped_and_reported() -> None:
    request = CharacterBuilderRequest(
        name="Boundary Clamp",
        proportions=CharacterProportions(
            shoulder_width=-2.0,
            torso_length=99.0,
            waist_width=0.0,
            hip_width=2.0,
            arm_length=0.1,
            leg_length=2.0,
            head_size=float("inf"),
            asymmetry=-1.0,
        ),
    )

    result = build_procedural_character(request)
    codes = {diagnostic.code for diagnostic in result.diagnostics}

    assert "REQUEST_CLAMPED_VALUE" in codes
    assert "REQUEST_NONFINITE_VALUE" in codes
    assert validate_character(result.character) == []
    assert result.normalized_request.proportions.shoulder_width == 0.75
    assert result.normalized_request.proportions.torso_length == 1.18
    assert result.normalized_request.proportions.head_size == 1.0


def test_svg_export_helpers_emit_part_and_combined_preview() -> None:
    result = build_procedural_character(PRESET_REQUESTS[1])
    head = next(
        attachment for attachment in result.character.attachments if attachment.id == "part_head"
    )

    part_svg = primitive_attachment_svg(head)
    combined_svg = combined_character_svg(result.character)

    assert 'data-part-id="part_head"' in part_svg
    assert "<ellipse" in part_svg
    assert f'data-character-id="{result.character.id}"' in combined_svg
    assert 'data-part-id="part_torso"' in combined_svg


@settings(max_examples=40)
@given(
    shoulder_width=st.floats(min_value=-2.0, max_value=3.0, allow_nan=False),
    torso_length=st.floats(min_value=-2.0, max_value=3.0, allow_nan=False),
    waist_width=st.floats(min_value=-2.0, max_value=3.0, allow_nan=False),
    hip_width=st.floats(min_value=-2.0, max_value=3.0, allow_nan=False),
    arm_length=st.floats(min_value=-2.0, max_value=3.0, allow_nan=False),
    leg_length=st.floats(min_value=-2.0, max_value=3.0, allow_nan=False),
    head_size=st.floats(min_value=-2.0, max_value=3.0, allow_nan=False),
    asymmetry=st.floats(min_value=-1.0, max_value=1.0, allow_nan=False),
)
def test_generated_character_invariants_hold_for_clamped_proportions(
    shoulder_width: float,
    torso_length: float,
    waist_width: float,
    hip_width: float,
    arm_length: float,
    leg_length: float,
    head_size: float,
    asymmetry: float,
) -> None:
    result = build_procedural_character(
        CharacterBuilderRequest(
            name="Property Human",
            proportions=CharacterProportions(
                shoulder_width=shoulder_width,
                torso_length=torso_length,
                waist_width=waist_width,
                hip_width=hip_width,
                arm_length=arm_length,
                leg_length=leg_length,
                head_size=head_size,
                asymmetry=asymmetry,
            ),
        )
    )

    assert validate_character(result.character) == []
    assert all(diagnostic.severity != "error" for diagnostic in result.diagnostics)
    assert all(bone.length > 0.0 for bone in result.character.rig.bones if bone.id != "root")
    assert all(
        (
            attachment.kind == "primitive"
            and attachment.primitive is not None
            and attachment.primitive.size[0] > 0.0
            and attachment.primitive.size[1] > 0.0
        )
        or (
            attachment.kind == "mesh"
            and attachment.mesh is not None
            and len(attachment.mesh.vertices) >= 3
            and all(
                abs(sum(weight.weight for weight in vertex.weights) - 1.0) <= 1e-6
                for vertex in attachment.mesh.weights
            )
        )
        for attachment in result.character.attachments
    )
