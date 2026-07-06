"""Character definition: a rig plus visual attachments."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from app.domain.common import DomainModel, Point2, TransformSpec
from app.domain.errors import ValidationIssue
from app.domain.ids import AssetId, AttachmentId, BoneId, CharacterId
from app.domain.rig import RigDefinition, validate_rig

type AttachmentKind = Literal["primitive", "svg", "png", "mesh"]
type PrimitiveAttachmentShape = Literal["capsule", "ellipse", "rectangle"]
type Matrix2D = tuple[float, float, float, float, float, float]


class PrimitiveAttachmentSpec(DomainModel):
    shape: PrimitiveAttachmentShape = "capsule"
    size: Point2 = (0.4, 0.16)
    fill: str = Field(default="#e6b17a", pattern=r"^#[0-9a-fA-F]{6}$")
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)


class MeshVertexWeight(DomainModel):
    bone_id: BoneId
    weight: float = Field(ge=0.0, le=1.0)


class MeshVertexWeights(DomainModel):
    weights: tuple[MeshVertexWeight, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_weights(self) -> MeshVertexWeights:
        total = sum(weight.weight for weight in self.weights)
        if abs(total - 1.0) > 1e-6:
            raise ValueError("mesh vertex weights must sum to 1.0")
        bone_ids = [weight.bone_id for weight in self.weights]
        if len(set(bone_ids)) != len(bone_ids):
            raise ValueError("mesh vertex weights must not repeat a bone_id")
        return self


class MeshTriangle(DomainModel):
    indices: tuple[int, int, int]

    @model_validator(mode="after")
    def _check_indices(self) -> MeshTriangle:
        if any(index < 0 for index in self.indices):
            raise ValueError("mesh triangle indices must be non-negative")
        if len(set(self.indices)) != 3:
            raise ValueError("mesh triangle indices must be distinct")
        return self


class MeshBindPose(DomainModel):
    bone_id: BoneId
    bind_matrix: Matrix2D
    inverse_bind_matrix: Matrix2D


class MeshAttachmentSpec(DomainModel):
    """A deformable attachment skinned by weighted bone influences."""

    vertices: tuple[Point2, ...] = Field(min_length=3)
    triangles: tuple[MeshTriangle, ...] = Field(min_length=1)
    weights: tuple[MeshVertexWeights, ...] = Field(min_length=3)
    bind_pose: tuple[MeshBindPose, ...] = Field(min_length=1)
    fill: str = Field(default="#e6b17a", pattern=r"^#[0-9a-fA-F]{6}$")
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    smoothing: float = Field(default=0.0, ge=0.0, le=1.0)
    secondary_motion: float = Field(default=0.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _check_lengths(self) -> MeshAttachmentSpec:
        if len(self.weights) != len(self.vertices):
            raise ValueError("mesh weights length must match vertices length")
        vertex_count = len(self.vertices)
        for triangle in self.triangles:
            if any(index >= vertex_count for index in triangle.indices):
                raise ValueError("mesh triangle index exceeds vertex count")
        bind_bone_ids = [entry.bone_id for entry in self.bind_pose]
        if len(set(bind_bone_ids)) != len(bind_bone_ids):
            raise ValueError("mesh bind pose must not repeat a bone_id")
        return self


class AttachmentDefinition(DomainModel):
    """A visual layer owned by one bone, either rigid or weighted mesh."""

    id: AttachmentId
    bone_id: BoneId
    kind: AttachmentKind
    asset_id: AssetId | None = None
    primitive: PrimitiveAttachmentSpec | None = None
    mesh: MeshAttachmentSpec | None = None
    pivot: Point2 = (0.0, 0.0)
    transform: TransformSpec = TransformSpec()
    z_index: int = 0
    visible: bool = True

    @model_validator(mode="after")
    def _check_payload(self) -> AttachmentDefinition:
        if self.kind == "primitive" and self.primitive is None:
            return self.model_copy(update={"primitive": PrimitiveAttachmentSpec()})
        if self.kind == "mesh" and self.mesh is None:
            raise ValueError("mesh attachments require a mesh payload")
        if self.kind != "mesh" and self.mesh is not None:
            raise ValueError("only mesh attachments may include a mesh payload")
        return self


class CharacterDefinition(DomainModel):
    id: CharacterId
    name: str = Field(min_length=1)
    rig: RigDefinition
    attachments: tuple[AttachmentDefinition, ...] = ()


def validate_character(
    character: CharacterDefinition, path_prefix: str = ""
) -> list[ValidationIssue]:
    prefix = f"{path_prefix}." if path_prefix else ""
    issues = validate_rig(character.rig, f"{prefix}rig")

    bone_ids = {bone.id for bone in character.rig.bones}
    seen_attachments: set[str] = set()
    for index, attachment in enumerate(character.attachments):
        attachment_path = f"{prefix}attachments[{index}]"
        if attachment.id in seen_attachments:
            issues.append(
                ValidationIssue(
                    "CHAR_DUPLICATE_ATTACHMENT_ID",
                    f"attachment id {attachment.id!r} is defined more than once",
                    f"{attachment_path}.id",
                )
            )
        seen_attachments.add(attachment.id)
        if attachment.bone_id not in bone_ids:
            issues.append(
                ValidationIssue(
                    "CHAR_ATTACHMENT_UNKNOWN_BONE",
                    f"attachment {attachment.id!r} references unknown bone {attachment.bone_id!r}",
                    f"{attachment_path}.bone_id",
                )
            )
        if attachment.kind in {"svg", "png"} and attachment.asset_id is None:
            issues.append(
                ValidationIssue(
                    "CHAR_ATTACHMENT_ASSET_MISSING",
                    f"attachment {attachment.id!r} of kind {attachment.kind!r} "
                    "requires an asset_id",
                    f"{attachment_path}.asset_id",
                )
            )
        if attachment.kind == "mesh" and attachment.mesh is not None:
            bind_bone_ids = {entry.bone_id for entry in attachment.mesh.bind_pose}
            for bind_index, bind in enumerate(attachment.mesh.bind_pose):
                if bind.bone_id not in bone_ids:
                    issues.append(
                        ValidationIssue(
                            "CHAR_MESH_UNKNOWN_BONE",
                            f"mesh attachment {attachment.id!r} bind pose references "
                            f"unknown bone {bind.bone_id!r}",
                            f"{attachment_path}.mesh.bind_pose[{bind_index}].bone_id",
                        )
                    )
            for vertex_index, vertex_weights in enumerate(attachment.mesh.weights):
                for weight_index, weight in enumerate(vertex_weights.weights):
                    if weight.bone_id not in bone_ids:
                        issues.append(
                            ValidationIssue(
                                "CHAR_MESH_UNKNOWN_BONE",
                                f"mesh attachment {attachment.id!r} vertex {vertex_index} "
                                f"references unknown bone {weight.bone_id!r}",
                                f"{attachment_path}.mesh.weights[{vertex_index}]."
                                f"weights[{weight_index}].bone_id",
                            )
                        )
                    if weight.bone_id not in bind_bone_ids:
                        issues.append(
                            ValidationIssue(
                                "CHAR_MESH_MISSING_BIND_POSE",
                                f"mesh attachment {attachment.id!r} vertex {vertex_index} "
                                f"references bone {weight.bone_id!r} without a bind pose",
                                f"{attachment_path}.mesh.weights[{vertex_index}]."
                                f"weights[{weight_index}].bone_id",
                            )
                        )
    return issues
