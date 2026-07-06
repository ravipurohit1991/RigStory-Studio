from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain.blueprint import CANNED_BLUEPRINT, merge_regional_blueprint_update
from app.domain.character import (
    AttachmentDefinition,
    MeshAttachmentSpec,
    MeshBindPose,
    MeshTriangle,
    MeshVertexWeight,
    MeshVertexWeights,
    validate_character,
)
from app.domain.character_builder import (
    CharacterBuilderRequest,
    build_procedural_character,
)
from app.domain.mesh_skinning import skin_attachment_vertices


def test_weighted_clothing_meshes_validate_and_skin_deterministically() -> None:
    result = build_procedural_character(
        CharacterBuilderRequest(name="Mesh Jacket", top="jacket", bottom="trousers")
    )
    character = result.character
    sleeve = next(part for part in character.attachments if part.id == "mesh_sleeve_l")
    trouser = next(part for part in character.attachments if part.id == "mesh_trouser_l")

    assert validate_character(character) == []
    assert sleeve.mesh is not None
    assert trouser.mesh is not None
    assert all(
        abs(sum(weight.weight for weight in vertex.weights) - 1.0) <= 1e-6
        for vertex in sleeve.mesh.weights
    )

    first = skin_attachment_vertices(sleeve, character.rig)
    second = skin_attachment_vertices(sleeve, character.rig)

    assert first == second
    assert len(first) == len(sleeve.mesh.vertices)
    assert first[0].x == pytest.approx(sleeve.mesh.vertices[0][0])
    assert first[0].y == pytest.approx(sleeve.mesh.vertices[0][1])


def test_weighted_sleeve_survives_bent_elbow_without_rigid_gap() -> None:
    result = build_procedural_character(
        CharacterBuilderRequest(name="Bent Sleeve", top="sweater")
    )
    sleeve = next(part for part in result.character.attachments if part.id == "mesh_sleeve_l")
    rig = result.character.rig
    bent_bones = tuple(
        bone.model_copy(
            update={
                "setup_transform": bone.setup_transform.model_copy(
                    update={"rotation_deg": 62.0}
                )
            }
        )
        if bone.id == "forearm_l"
        else bone
        for bone in rig.bones
    )
    bent_rig = rig.model_copy(update={"bones": bent_bones})

    skinned = skin_attachment_vertices(sleeve, bent_rig)

    assert sleeve.mesh is not None
    elbow_bottom = skinned[2]
    elbow_top = skinned[3]
    assert elbow_bottom.x < skinned[4].x
    assert elbow_top.x < skinned[5].x
    assert abs(elbow_top.y - elbow_bottom.y) > 0.01


def test_invalid_mesh_bone_reference_is_reported() -> None:
    result = build_procedural_character(CharacterBuilderRequest(name="Bad Mesh"))
    character = result.character
    bad = AttachmentDefinition(
        id="mesh_bad",
        bone_id="upper_arm_l",
        kind="mesh",
        mesh=MeshAttachmentSpec(
            vertices=((0.0, 0.0), (1.0, 0.0), (0.0, 1.0)),
            triangles=(MeshTriangle(indices=(0, 1, 2)),),
            weights=(
                MeshVertexWeights(weights=(MeshVertexWeight(bone_id="ghost", weight=1.0),)),
                MeshVertexWeights(weights=(MeshVertexWeight(bone_id="upper_arm_l", weight=1.0),)),
                MeshVertexWeights(weights=(MeshVertexWeight(bone_id="upper_arm_l", weight=1.0),)),
            ),
            bind_pose=(
                MeshBindPose(
                    bone_id="upper_arm_l",
                    bind_matrix=(1, 0, 0, 1, 0, 0),
                    inverse_bind_matrix=(1, 0, 0, 1, 0, 0),
                ),
            ),
        ),
    )

    issues = validate_character(
        character.model_copy(update={"attachments": (*character.attachments, bad)})
    )

    assert {issue.code for issue in issues} >= {
        "CHAR_MESH_UNKNOWN_BONE",
        "CHAR_MESH_MISSING_BIND_POSE",
    }


def test_mesh_weights_must_sum_to_one() -> None:
    with pytest.raises(ValidationError, match=r"sum to 1\.0"):
        MeshVertexWeights(
            weights=(
                MeshVertexWeight(bone_id="upper_arm_l", weight=0.25),
                MeshVertexWeight(bone_id="forearm_l", weight=0.25),
            )
        )


def test_regional_blueprint_update_locks_unrelated_fields() -> None:
    update = CANNED_BLUEPRINT.model_copy(
        update={
            "character_name": "Different Name",
            "appearance": CANNED_BLUEPRINT.appearance.model_copy(
                update={
                    "hair": CANNED_BLUEPRINT.appearance.hair.model_copy(
                        update={"style": "long", "color": "#101010"}
                    )
                }
            ),
            "clothing": (),
            "warnings": ("hair changed",),
        }
    )

    merged = merge_regional_blueprint_update(CANNED_BLUEPRINT, update, "hair")

    assert merged.character_name == CANNED_BLUEPRINT.character_name
    assert merged.proportions == CANNED_BLUEPRINT.proportions
    assert merged.clothing == CANNED_BLUEPRINT.clothing
    assert merged.appearance.hair.style == "long"
    assert "hair changed" in merged.warnings
