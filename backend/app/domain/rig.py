"""Rig and bone definitions with hierarchy validation and FK evaluation.

Bones extend along their local +X axis by ``length``. A bone's setup
transform is local to its parent and immutable during animation evaluation.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from app.domain.common import DomainModel, TransformSpec
from app.domain.errors import DomainValidationError, ValidationIssue
from app.domain.ids import BoneId, RigId
from app.domain.math2d.affine import Affine2
from app.domain.math2d.vec2 import Vec2


class JointLimit(DomainModel):
    min_rotation_deg: float
    max_rotation_deg: float
    soft_zone_deg: float = Field(default=0.0, ge=0.0)

    @model_validator(mode="after")
    def _check_range(self) -> JointLimit:
        if self.min_rotation_deg > self.max_rotation_deg:
            raise ValueError(
                "joint limit is inverted: "
                f"min {self.min_rotation_deg} > max {self.max_rotation_deg}"
            )
        return self


class BoneDefinition(DomainModel):
    id: BoneId
    parent_id: BoneId | None = None
    setup_transform: TransformSpec = TransformSpec()
    length: float = Field(ge=0.0)
    joint_limit: JointLimit | None = None
    tags: tuple[str, ...] = ()


class RigDefinition(DomainModel):
    id: RigId
    name: str = Field(min_length=1)
    bones: tuple[BoneDefinition, ...]


def validate_rig(rig: RigDefinition, path_prefix: str = "") -> list[ValidationIssue]:
    """Cross-bone invariants: unique IDs, single root, resolvable acyclic hierarchy."""
    issues: list[ValidationIssue] = []
    prefix = f"{path_prefix}." if path_prefix else ""

    if not rig.bones:
        issues.append(ValidationIssue("RIG_NO_BONES", "rig has no bones", f"{prefix}bones"))
        return issues

    by_id: dict[str, BoneDefinition] = {}
    for index, bone in enumerate(rig.bones):
        if bone.id in by_id:
            issues.append(
                ValidationIssue(
                    "RIG_DUPLICATE_BONE_ID",
                    f"bone id {bone.id!r} is defined more than once",
                    f"{prefix}bones[{index}].id",
                )
            )
        else:
            by_id[bone.id] = bone

    roots = [bone for bone in rig.bones if bone.parent_id is None]
    if not roots:
        issues.append(
            ValidationIssue("RIG_NO_ROOT", "no bone has a null parent_id", f"{prefix}bones")
        )
    elif len(roots) > 1:
        root_ids = ", ".join(bone.id for bone in roots)
        issues.append(
            ValidationIssue(
                "RIG_MULTIPLE_ROOTS",
                f"expected exactly one root bone, found: {root_ids}",
                f"{prefix}bones",
            )
        )

    for index, bone in enumerate(rig.bones):
        if bone.parent_id is None:
            continue
        if bone.parent_id == bone.id:
            issues.append(
                ValidationIssue(
                    "RIG_SELF_PARENT",
                    f"bone {bone.id!r} is its own parent",
                    f"{prefix}bones[{index}].parent_id",
                )
            )
        elif bone.parent_id not in by_id:
            issues.append(
                ValidationIssue(
                    "RIG_MISSING_PARENT",
                    f"bone {bone.id!r} references unknown parent {bone.parent_id!r}",
                    f"{prefix}bones[{index}].parent_id",
                )
            )

    # Cycle detection over resolvable parents.
    for index, bone in enumerate(rig.bones):
        seen: set[str] = {bone.id}
        current = bone
        while current.parent_id is not None:
            parent = by_id.get(current.parent_id)
            if parent is None or parent.id == current.id:
                break
            if parent.id in seen:
                issues.append(
                    ValidationIssue(
                        "RIG_CYCLE",
                        f"bone {bone.id!r} participates in a parent cycle",
                        f"{prefix}bones[{index}].parent_id",
                    )
                )
                break
            seen.add(parent.id)
            current = parent

    # Connectivity: every bone must be reachable from the single root.
    if len(roots) == 1 and not any(issue.code == "RIG_CYCLE" for issue in issues):
        children: dict[str, list[str]] = {bone.id: [] for bone in by_id.values()}
        for bone in by_id.values():
            if bone.parent_id is not None and bone.parent_id in children:
                children[bone.parent_id].append(bone.id)
        reachable: set[str] = set()
        stack = [roots[0].id]
        while stack:
            bone_id = stack.pop()
            if bone_id in reachable:
                continue
            reachable.add(bone_id)
            stack.extend(children[bone_id])
        for index, bone in enumerate(rig.bones):
            if bone.id not in reachable:
                issues.append(
                    ValidationIssue(
                        "RIG_DISCONNECTED_BONE",
                        f"bone {bone.id!r} is not reachable from root {roots[0].id!r}",
                        f"{prefix}bones[{index}]",
                    )
                )

    return issues


def compute_world_transforms(rig: RigDefinition) -> dict[str, Affine2]:
    """World matrix per bone from setup transforms, root to leaf."""
    issues = validate_rig(rig)
    if issues:
        raise DomainValidationError(tuple(issues))

    by_id = {bone.id: bone for bone in rig.bones}
    children: dict[str, list[str]] = {bone.id: [] for bone in rig.bones}
    root_id = ""
    for bone in rig.bones:
        if bone.parent_id is None:
            root_id = bone.id
        else:
            children[bone.parent_id].append(bone.id)

    world: dict[str, Affine2] = {}
    stack = [(root_id, Affine2.identity())]
    while stack:
        bone_id, parent_world = stack.pop()
        bone = by_id[bone_id]
        bone_world = bone.setup_transform.to_transform2d().compose_affine(parent_world)
        world[bone_id] = bone_world
        for child_id in children[bone_id]:
            stack.append((child_id, bone_world))
    return world


def compute_bone_endpoints(rig: RigDefinition) -> dict[str, tuple[Vec2, Vec2]]:
    """World-space (origin, tip) per bone; the tip lies ``length`` along local +X."""
    world = compute_world_transforms(rig)
    endpoints: dict[str, tuple[Vec2, Vec2]] = {}
    by_id = {bone.id: bone for bone in rig.bones}
    for bone_id, matrix in world.items():
        origin = matrix.apply_point(Vec2.zero())
        tip = matrix.apply_point(Vec2(by_id[bone_id].length, 0.0))
        endpoints[bone_id] = (origin, tip)
    return endpoints
