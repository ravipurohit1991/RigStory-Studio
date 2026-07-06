"""Deterministic CPU skinning for weighted 2D mesh attachments."""

from __future__ import annotations

from app.domain.character import AttachmentDefinition, Matrix2D, MeshVertexWeight
from app.domain.math2d.affine import Affine2
from app.domain.math2d.vec2 import Vec2
from app.domain.rig import RigDefinition, compute_world_transforms


def matrix_to_affine(matrix: Matrix2D) -> Affine2:
    a, b, c, d, tx, ty = matrix
    return Affine2(a, b, c, d, tx, ty)


def affine_to_matrix(matrix: Affine2) -> Matrix2D:
    return (matrix.a, matrix.b, matrix.c, matrix.d, matrix.tx, matrix.ty)


def normalize_vertex_weights(
    weights: tuple[MeshVertexWeight, ...],
) -> tuple[MeshVertexWeight, ...]:
    """Return non-zero weights normalized to a sum of exactly one."""
    positive = tuple(weight for weight in weights if weight.weight > 0.0)
    if not positive:
        raise ValueError("at least one positive mesh weight is required")
    total = sum(weight.weight for weight in positive)
    if total <= 0.0:
        raise ValueError("mesh weight total must be positive")
    normalized = tuple(
        MeshVertexWeight(bone_id=weight.bone_id, weight=weight.weight / total)
        for weight in positive
    )
    correction = 1.0 - sum(weight.weight for weight in normalized)
    if correction != 0.0:
        last = normalized[-1]
        normalized = (
            *normalized[:-1],
            MeshVertexWeight(bone_id=last.bone_id, weight=last.weight + correction),
        )
    return normalized


def skin_attachment_vertices(
    attachment: AttachmentDefinition,
    rig: RigDefinition,
) -> tuple[Vec2, ...]:
    """Evaluate skinned attachment vertices in the owning attachment's local space.

    Mesh vertices are serialized in attachment-local bind-pose coordinates.
    Each bind pose stores a bone matrix relative to the attachment owner and its
    inverse. At evaluation time, current bone matrices are converted into the
    same owner-relative space, multiplied by inverse bind, and blended by the
    normalized vertex weights.
    """
    if attachment.kind != "mesh" or attachment.mesh is None:
        raise ValueError("skin_attachment_vertices requires a mesh attachment")

    worlds = compute_world_transforms(rig)
    owner_world = worlds.get(attachment.bone_id)
    if owner_world is None:
        raise ValueError(f"attachment owner bone {attachment.bone_id!r} is missing")
    owner_inverse = owner_world.inverse()
    current_by_bone: dict[str, Affine2] = {}
    for bone_id, world in worlds.items():
        current_by_bone[bone_id] = owner_inverse.multiply(world)

    inverse_bind_by_bone = {
        bind.bone_id: matrix_to_affine(bind.inverse_bind_matrix)
        for bind in attachment.mesh.bind_pose
    }

    skinned: list[Vec2] = []
    for vertex, vertex_weights in zip(
        attachment.mesh.vertices, attachment.mesh.weights, strict=True
    ):
        source = Vec2(vertex[0], vertex[1])
        x = 0.0
        y = 0.0
        for weight in normalize_vertex_weights(vertex_weights.weights):
            current = current_by_bone.get(weight.bone_id)
            inverse_bind = inverse_bind_by_bone.get(weight.bone_id)
            if current is None or inverse_bind is None:
                raise ValueError(f"mesh influence bone {weight.bone_id!r} is missing")
            transformed = current.multiply(inverse_bind).apply_point(source)
            x += transformed.x * weight.weight
            y += transformed.y * weight.weight
        skinned.append(Vec2(x, y))
    return tuple(skinned)
