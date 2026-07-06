"""Deterministic procedural human character builder.

This module deliberately avoids LLM input. A request is normalized into safe
parameter ranges, then compiled into the ordinary editable
``CharacterDefinition`` used by the manual rig editor.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from html import escape
from typing import Literal

from pydantic import Field

from app.domain.canonical import JsonValue, canonical_json_dumps
from app.domain.character import (
    AttachmentDefinition,
    CharacterDefinition,
    MeshAttachmentSpec,
    MeshBindPose,
    MeshTriangle,
    MeshVertexWeight,
    MeshVertexWeights,
    PrimitiveAttachmentSpec,
    validate_character,
)
from app.domain.common import DomainModel, Point2, TransformSpec
from app.domain.ids import BoneId, CharacterId, RigId
from app.domain.math2d.affine import Affine2
from app.domain.rig import BoneDefinition, JointLimit, RigDefinition, compute_world_transforms

GENERATOR_VERSION = "procedural-human-v1"

type Presentation = Literal["masculine", "feminine", "neutral"]
type AgeCategory = Literal["child", "teen", "adult", "older_adult"]
type HeightClass = Literal["short", "average", "tall"]
type BodyBuild = Literal["slender", "average", "sturdy", "broad"]
type HairStyle = Literal["bald", "short", "bob", "curly", "long", "coily"]
type FaceShape = Literal["round", "oval", "square", "heart", "long"]
type TopClothing = Literal["tshirt", "shirt", "sweater", "jacket"]
type BottomClothing = Literal["trousers", "shorts", "skirt"]
type Footwear = Literal["shoes", "boots", "sneakers"]
type Outerwear = Literal["none", "vest", "coat"]
type ArtStyle = Literal[
    "flat_vector",
    "cartoon",
    "graphic_novel",
    "paper_cutout",
    "silhouette",
]
type DiagnosticSeverity = Literal["info", "warning", "error"]
type RegenerationRegion = Literal["all", "hair", "face", "clothing"]
type GeneratedConstraintType = Literal["two_bone_ik", "look_at"]

SIDES: tuple[Literal["l", "r"], ...] = ("l", "r")


class CharacterProportions(DomainModel):
    shoulder_width: float = 1.0
    torso_length: float = 1.0
    waist_width: float = 1.0
    hip_width: float = 1.0
    arm_length: float = 1.0
    leg_length: float = 1.0
    head_size: float = 1.0
    asymmetry: float = 0.0


class CharacterPalette(DomainModel):
    skin: str = Field(default="#c98f62", pattern=r"^#[0-9a-fA-F]{6}$")
    hair: str = Field(default="#3d2a1e", pattern=r"^#[0-9a-fA-F]{6}$")
    top: str = Field(default="#2f6f73", pattern=r"^#[0-9a-fA-F]{6}$")
    bottom: str = Field(default="#2f3a56", pattern=r"^#[0-9a-fA-F]{6}$")
    shoes: str = Field(default="#2b2b2b", pattern=r"^#[0-9a-fA-F]{6}$")
    accent: str = Field(default="#f0d36b", pattern=r"^#[0-9a-fA-F]{6}$")


class CharacterBuilderRequest(DomainModel):
    name: str = Field(default="Procedural Human", min_length=1)
    presentation: Presentation = "neutral"
    age_category: AgeCategory = "adult"
    height: HeightClass = "average"
    build: BodyBuild = "average"
    proportions: CharacterProportions = CharacterProportions()
    palette: CharacterPalette = CharacterPalette()
    hair_style: HairStyle = "short"
    face_shape: FaceShape = "oval"
    top: TopClothing = "tshirt"
    bottom: BottomClothing = "trousers"
    footwear: Footwear = "shoes"
    outerwear: Outerwear = "none"
    style: ArtStyle = "flat_vector"


class BuilderDiagnostic(DomainModel):
    code: str
    severity: DiagnosticSeverity
    message: str
    path: str
    original_value: float | str | None = None
    normalized_value: float | str | None = None


class GeneratedConstraintDefinition(DomainModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    type: GeneratedConstraintType
    bone_ids: tuple[BoneId, ...]
    effector_bone_id: BoneId
    tags: tuple[str, ...] = ()


class CharacterBuilderResult(DomainModel):
    generator_version: str = GENERATOR_VERSION
    normalized_request: CharacterBuilderRequest
    character: CharacterDefinition
    constraints: tuple[GeneratedConstraintDefinition, ...] = ()
    diagnostics: tuple[BuilderDiagnostic, ...] = ()


@dataclass(frozen=True, slots=True)
class NumericRange:
    path: str
    minimum: float
    default: float
    maximum: float


@dataclass(frozen=True, slots=True)
class HumanDimensions:
    height_scale: float
    hip_y: float
    hip_length: float
    pelvis_width: float
    waist_width: float
    shoulder_width: float
    torso_lower: float
    torso_upper: float
    chest_length: float
    neck_length: float
    head_length: float
    head_width: float
    clavicle_length: float
    upper_arm_length: float
    forearm_length: float
    hand_length: float
    thigh_length: float
    shin_length: float
    foot_length: float
    toe_length: float
    limb_thickness: float
    arm_thickness: float
    leg_thickness: float
    side_asymmetry: float


PROPORTION_RANGES: tuple[NumericRange, ...] = (
    NumericRange("proportions.shoulder_width", 0.75, 1.0, 1.25),
    NumericRange("proportions.torso_length", 0.82, 1.0, 1.18),
    NumericRange("proportions.waist_width", 0.72, 1.0, 1.18),
    NumericRange("proportions.hip_width", 0.75, 1.0, 1.25),
    NumericRange("proportions.arm_length", 0.84, 1.0, 1.18),
    NumericRange("proportions.leg_length", 0.84, 1.0, 1.2),
    NumericRange("proportions.head_size", 0.86, 1.0, 1.16),
    NumericRange("proportions.asymmetry", 0.0, 0.0, 0.04),
)


def _proportion_values(proportions: CharacterProportions) -> dict[str, float]:
    return {
        "proportions.shoulder_width": proportions.shoulder_width,
        "proportions.torso_length": proportions.torso_length,
        "proportions.waist_width": proportions.waist_width,
        "proportions.hip_width": proportions.hip_width,
        "proportions.arm_length": proportions.arm_length,
        "proportions.leg_length": proportions.leg_length,
        "proportions.head_size": proportions.head_size,
        "proportions.asymmetry": proportions.asymmetry,
    }


def _diagnostic(
    code: str,
    severity: DiagnosticSeverity,
    message: str,
    path: str,
    original_value: float | str | None = None,
    normalized_value: float | str | None = None,
) -> BuilderDiagnostic:
    return BuilderDiagnostic(
        code=code,
        severity=severity,
        message=message,
        path=path,
        original_value=original_value,
        normalized_value=normalized_value,
    )


def normalize_character_request(
    request: CharacterBuilderRequest,
) -> tuple[CharacterBuilderRequest, tuple[BuilderDiagnostic, ...]]:
    diagnostics: list[BuilderDiagnostic] = []
    values = _proportion_values(request.proportions)
    normalized_values: dict[str, float] = {}
    for range_spec in PROPORTION_RANGES:
        raw = values[range_spec.path]
        if not math.isfinite(raw):
            diagnostics.append(
                _diagnostic(
                    "REQUEST_NONFINITE_VALUE",
                    "warning",
                    f"{range_spec.path} was non-finite and was reset to its default",
                    range_spec.path,
                    str(raw),
                    range_spec.default,
                )
            )
            clamped_value = range_spec.default
        else:
            clamped_value = min(max(raw, range_spec.minimum), range_spec.maximum)
            if clamped_value != raw:
                diagnostics.append(
                    _diagnostic(
                        "REQUEST_CLAMPED_VALUE",
                        "info",
                        f"{range_spec.path} was clamped into the supported range",
                        range_spec.path,
                        raw,
                        clamped_value,
                    )
                )
        normalized_values[range_spec.path.removeprefix("proportions.")] = clamped_value

    normalized_request = request.model_copy(
        update={
            "proportions": CharacterProportions(
                shoulder_width=normalized_values["shoulder_width"],
                torso_length=normalized_values["torso_length"],
                waist_width=normalized_values["waist_width"],
                hip_width=normalized_values["hip_width"],
                arm_length=normalized_values["arm_length"],
                leg_length=normalized_values["leg_length"],
                head_size=normalized_values["head_size"],
                asymmetry=normalized_values["asymmetry"],
            )
        }
    )
    return normalized_request, tuple(diagnostics)


def _stable_suffix(request: CharacterBuilderRequest) -> str:
    payload: JsonValue = request.model_dump(mode="json")
    digest = hashlib.sha256(
        f"{GENERATOR_VERSION}:{canonical_json_dumps(payload)}".encode()
    ).hexdigest()
    return digest[:16]


def _character_id(request: CharacterBuilderRequest) -> CharacterId:
    return f"char_proc_{_stable_suffix(request)}"


def _rig_id(request: CharacterBuilderRequest) -> RigId:
    return f"rig_proc_{_stable_suffix(request)}"


def _age_scale(age_category: AgeCategory) -> float:
    return {
        "child": 0.74,
        "teen": 0.9,
        "adult": 1.0,
        "older_adult": 0.97,
    }[age_category]


def _height_scale(height: HeightClass) -> float:
    return {
        "short": 0.92,
        "average": 1.0,
        "tall": 1.1,
    }[height]


def _build_width_scale(build: BodyBuild) -> float:
    return {
        "slender": 0.88,
        "average": 1.0,
        "sturdy": 1.1,
        "broad": 1.2,
    }[build]


def _presentation_width_scales(presentation: Presentation) -> tuple[float, float, float]:
    if presentation == "masculine":
        return (1.08, 1.0, 0.96)
    if presentation == "feminine":
        return (0.96, 0.9, 1.08)
    return (1.0, 0.97, 1.0)


def _dimensions(request: CharacterBuilderRequest) -> HumanDimensions:
    p = request.proportions
    age = _age_scale(request.age_category)
    height = _height_scale(request.height)
    scale = age * height
    build_width = _build_width_scale(request.build)
    shoulder_shape, waist_shape, hip_shape = _presentation_width_scales(request.presentation)
    if request.age_category == "child":
        head_age = 1.16
        limb_age = 0.9
    elif request.age_category == "teen":
        head_age = 1.06
        limb_age = 0.97
    else:
        head_age = 1.0
        limb_age = 1.0

    torso_lower = 0.3 * scale * p.torso_length
    torso_upper = 0.32 * scale * p.torso_length
    chest_length = 0.34 * scale * p.torso_length
    thigh = 0.82 * scale * p.leg_length * limb_age
    shin = 0.74 * scale * p.leg_length * limb_age
    foot = 0.3 * scale
    hip_y = thigh + shin + 0.12 * scale
    shoulder_width = 0.64 * scale * p.shoulder_width * shoulder_shape * build_width
    waist_width = 0.42 * scale * p.waist_width * waist_shape * build_width
    pelvis_width = 0.5 * scale * p.hip_width * hip_shape * build_width
    head_length = 0.42 * scale * p.head_size * head_age
    head_width = 0.36 * scale * p.head_size * head_age
    limb_thickness = 0.15 * scale * build_width
    return HumanDimensions(
        height_scale=scale,
        hip_y=hip_y,
        hip_length=0.2 * scale,
        pelvis_width=pelvis_width,
        waist_width=waist_width,
        shoulder_width=shoulder_width,
        torso_lower=torso_lower,
        torso_upper=torso_upper,
        chest_length=chest_length,
        neck_length=0.14 * scale,
        head_length=head_length,
        head_width=head_width,
        clavicle_length=max(0.16 * scale, shoulder_width * 0.36),
        upper_arm_length=0.52 * scale * p.arm_length * limb_age,
        forearm_length=0.48 * scale * p.arm_length * limb_age,
        hand_length=0.19 * scale,
        thigh_length=thigh,
        shin_length=shin,
        foot_length=foot,
        toe_length=0.12 * scale,
        limb_thickness=limb_thickness,
        arm_thickness=limb_thickness * 0.82,
        leg_thickness=limb_thickness * 1.12,
        side_asymmetry=p.asymmetry,
    )


def _limit(minimum: float, maximum: float) -> JointLimit:
    return JointLimit(min_rotation_deg=minimum, max_rotation_deg=maximum)


def _bone(
    bone_id: str,
    parent_id: str | None,
    position: Point2,
    rotation_deg: float,
    length: float,
    tags: tuple[str, ...] = (),
    joint_limit: JointLimit | None = None,
) -> BoneDefinition:
    return BoneDefinition(
        id=bone_id,
        parent_id=parent_id,
        setup_transform=TransformSpec(position=position, rotation_deg=rotation_deg),
        length=round(length, 6),
        tags=tags,
        joint_limit=joint_limit,
    )


def _side_factor(side: Literal["l", "r"], asymmetry: float) -> float:
    return 1.0 + (asymmetry / 2.0 if side == "l" else -asymmetry / 2.0)


def generate_canonical_human_rig(request: CharacterBuilderRequest) -> RigDefinition:
    dims = _dimensions(request)
    shoulder_y = dims.shoulder_width / 2.0
    hip_y = dims.pelvis_width / 2.0
    eye_y = dims.head_width * 0.22
    bones: list[BoneDefinition] = [
        _bone("root", None, (0.0, 0.0), 0.0, 0.0),
        _bone("hips", "root", (0.0, dims.hip_y), 90.0, dims.hip_length, ("core",)),
        _bone(
            "spine_lower",
            "hips",
            (dims.hip_length, 0.0),
            0.0,
            dims.torso_lower,
            ("core",),
            _limit(-30.0, 30.0),
        ),
        _bone(
            "spine_upper",
            "spine_lower",
            (dims.torso_lower, 0.0),
            0.0,
            dims.torso_upper,
            ("core",),
            _limit(-32.0, 32.0),
        ),
        _bone(
            "chest",
            "spine_upper",
            (dims.torso_upper, 0.0),
            0.0,
            dims.chest_length,
            ("core",),
        ),
        _bone(
            "neck",
            "chest",
            (dims.chest_length, 0.0),
            0.0,
            dims.neck_length,
            ("core", "look_at"),
            _limit(-42.0, 42.0),
        ),
        _bone(
            "head",
            "neck",
            (dims.neck_length, 0.0),
            0.0,
            dims.head_length,
            ("core", "look_at"),
            _limit(-35.0, 35.0),
        ),
        _bone(
            "eye_l",
            "head",
            (dims.head_length * 0.56, eye_y),
            0.0,
            0.04 * dims.height_scale,
            ("face", "l", "look_at"),
        ),
        _bone(
            "eye_r",
            "head",
            (dims.head_length * 0.56, -eye_y),
            0.0,
            0.04 * dims.height_scale,
            ("face", "r", "look_at"),
        ),
    ]

    for side in SIDES:
        sign = 1.0 if side == "l" else -1.0
        factor = _side_factor(side, dims.side_asymmetry)
        bones.extend(
            [
                _bone(
                    f"clavicle_{side}",
                    "chest",
                    (dims.chest_length * 0.9, sign * shoulder_y * 0.22),
                    sign * 94.0,
                    dims.clavicle_length,
                    ("arm", side),
                ),
                _bone(
                    f"upper_arm_{side}",
                    f"clavicle_{side}",
                    (dims.clavicle_length, 0.0),
                    sign * 77.0,
                    dims.upper_arm_length * factor,
                    ("arm", side, "ik_chain"),
                    _limit(-170.0, 170.0),
                ),
                _bone(
                    f"forearm_{side}",
                    f"upper_arm_{side}",
                    (dims.upper_arm_length * factor, 0.0),
                    -sign * 5.0,
                    dims.forearm_length * factor,
                    ("arm", side, "ik_chain"),
                    _limit(-150.0, 6.0) if side == "l" else _limit(-6.0, 150.0),
                ),
                _bone(
                    f"hand_{side}",
                    f"forearm_{side}",
                    (dims.forearm_length * factor, 0.0),
                    0.0,
                    dims.hand_length * factor,
                    ("arm", side),
                    _limit(-55.0, 55.0),
                ),
                _bone(
                    f"thigh_{side}",
                    "hips",
                    (-dims.hip_length * 0.22, sign * hip_y * 0.43),
                    180.0,
                    dims.thigh_length * factor,
                    ("leg", side, "ik_chain"),
                    _limit(-120.0, 120.0),
                ),
                _bone(
                    f"shin_{side}",
                    f"thigh_{side}",
                    (dims.thigh_length * factor, 0.0),
                    0.0,
                    dims.shin_length * factor,
                    ("leg", side, "ik_chain"),
                    _limit(-6.0, 150.0) if side == "l" else _limit(-150.0, 6.0),
                ),
                _bone(
                    f"foot_{side}",
                    f"shin_{side}",
                    (dims.shin_length * factor, 0.0),
                    90.0,
                    dims.foot_length * factor,
                    ("leg", side),
                    _limit(-55.0, 55.0),
                ),
                _bone(
                    f"toe_{side}",
                    f"foot_{side}",
                    (dims.foot_length * factor, 0.0),
                    0.0,
                    dims.toe_length * factor,
                    ("leg", side),
                    _limit(-15.0, 35.0),
                ),
            ]
        )

    return RigDefinition(id=_rig_id(request), name="Procedural human rig", bones=tuple(bones))


def generate_rig_constraints(rig: RigDefinition) -> tuple[GeneratedConstraintDefinition, ...]:
    bone_ids = {bone.id for bone in rig.bones}
    constraints: list[GeneratedConstraintDefinition] = []
    for side in SIDES:
        arm_bones = (f"upper_arm_{side}", f"forearm_{side}", f"hand_{side}")
        leg_bones = (f"thigh_{side}", f"shin_{side}", f"foot_{side}")
        if set(arm_bones) <= bone_ids:
            constraints.append(
                GeneratedConstraintDefinition(
                    id=f"ik_arm_{side}",
                    type="two_bone_ik",
                    bone_ids=arm_bones,
                    effector_bone_id=f"hand_{side}",
                    tags=("arm", side),
                )
            )
        if set(leg_bones) <= bone_ids:
            constraints.append(
                GeneratedConstraintDefinition(
                    id=f"ik_leg_{side}",
                    type="two_bone_ik",
                    bone_ids=leg_bones,
                    effector_bone_id=f"foot_{side}",
                    tags=("leg", side),
                )
            )
    if {"neck", "head"} <= bone_ids:
        constraints.append(
            GeneratedConstraintDefinition(
                id="look_head",
                type="look_at",
                bone_ids=("neck", "head"),
                effector_bone_id="head",
                tags=("look_at",),
            )
        )
    if {"eye_l", "eye_r"} <= bone_ids:
        constraints.append(
            GeneratedConstraintDefinition(
                id="look_eyes",
                type="look_at",
                bone_ids=("eye_l", "eye_r"),
                effector_bone_id="eye_l",
                tags=("look_at", "face"),
            )
        )
    return tuple(constraints)


def _style_fill(request: CharacterBuilderRequest, color: str) -> str:
    if request.style == "silhouette":
        return "#222222"
    return color


def _style_opacity(request: CharacterBuilderRequest, base: float = 1.0) -> float:
    if request.style == "paper_cutout":
        return min(base, 0.94)
    return base


def _primitive(
    attachment_id: str,
    bone_id: str,
    shape: Literal["capsule", "ellipse", "rectangle"],
    size: Point2,
    fill: str,
    *,
    position: Point2 = (0.0, 0.0),
    pivot: Point2 = (0.0, 0.0),
    z_index: int = 0,
    opacity: float = 1.0,
) -> AttachmentDefinition:
    return AttachmentDefinition(
        id=attachment_id,
        bone_id=bone_id,
        kind="primitive",
        primitive=PrimitiveAttachmentSpec(
            shape=shape,
            size=(round(size[0], 6), round(size[1], 6)),
            fill=fill,
            opacity=opacity,
        ),
        pivot=pivot,
        transform=TransformSpec(position=position),
        z_index=z_index,
    )


def _matrix_tuple(matrix: Affine2) -> tuple[float, float, float, float, float, float]:
    return (
        round(matrix.a, 9),
        round(matrix.b, 9),
        round(matrix.c, 9),
        round(matrix.d, 9),
        round(matrix.tx, 9),
        round(matrix.ty, 9),
    )


def _relative_bind_pose(
    rig: RigDefinition,
    owner_bone_id: str,
    bone_ids: tuple[str, ...],
) -> tuple[MeshBindPose, ...]:
    worlds = compute_world_transforms(rig)
    owner_world = worlds[owner_bone_id]
    owner_inverse = owner_world.inverse()
    bind_pose: list[MeshBindPose] = []
    for bone_id in bone_ids:
        bind = owner_inverse.multiply(worlds[bone_id])
        bind_pose.append(
            MeshBindPose(
                bone_id=bone_id,
                bind_matrix=_matrix_tuple(bind),
                inverse_bind_matrix=_matrix_tuple(bind.inverse()),
            )
        )
    return tuple(bind_pose)


def _mesh_attachment(
    attachment_id: str,
    owner_bone_id: str,
    influence_bone_ids: tuple[str, str],
    rig: RigDefinition,
    length_a: float,
    length_b: float,
    width: float,
    fill: str,
    *,
    z_index: int,
    opacity: float = 1.0,
    secondary_motion: float = 0.0,
) -> AttachmentDefinition:
    seam_x = round(length_a, 6)
    end_x = round(length_a + length_b, 6)
    half = round(width / 2.0, 6)
    vertices: tuple[Point2, ...] = (
        (0.0, -half),
        (0.0, half),
        (seam_x, -half),
        (seam_x, half),
        (end_x, -half * 0.88),
        (end_x, half * 0.88),
    )
    a, b = influence_bone_ids
    weights = (
        MeshVertexWeights(weights=(MeshVertexWeight(bone_id=a, weight=1.0),)),
        MeshVertexWeights(weights=(MeshVertexWeight(bone_id=a, weight=1.0),)),
        MeshVertexWeights(
            weights=(
                MeshVertexWeight(bone_id=a, weight=0.5),
                MeshVertexWeight(bone_id=b, weight=0.5),
            )
        ),
        MeshVertexWeights(
            weights=(
                MeshVertexWeight(bone_id=a, weight=0.5),
                MeshVertexWeight(bone_id=b, weight=0.5),
            )
        ),
        MeshVertexWeights(weights=(MeshVertexWeight(bone_id=b, weight=1.0),)),
        MeshVertexWeights(weights=(MeshVertexWeight(bone_id=b, weight=1.0),)),
    )
    return AttachmentDefinition(
        id=attachment_id,
        bone_id=owner_bone_id,
        kind="mesh",
        mesh=MeshAttachmentSpec(
            vertices=vertices,
            triangles=(
                MeshTriangle(indices=(0, 2, 1)),
                MeshTriangle(indices=(1, 2, 3)),
                MeshTriangle(indices=(2, 4, 3)),
                MeshTriangle(indices=(3, 4, 5)),
            ),
            weights=weights,
            bind_pose=_relative_bind_pose(rig, owner_bone_id, influence_bone_ids),
            fill=fill,
            opacity=opacity,
            smoothing=0.7,
            secondary_motion=secondary_motion,
        ),
        z_index=z_index,
    )


def _hair_sizes(style: HairStyle, dims: HumanDimensions) -> tuple[Point2, Point2]:
    back_length = {
        "bald": 0.0,
        "short": 0.34,
        "bob": 0.46,
        "curly": 0.46,
        "long": 0.72,
        "coily": 0.52,
    }[style]
    front_length = {
        "bald": 0.0,
        "short": 0.18,
        "bob": 0.22,
        "curly": 0.26,
        "long": 0.28,
        "coily": 0.3,
    }[style]
    return (
        (max(0.01, dims.head_length * back_length), dims.head_width * 1.08),
        (max(0.01, dims.head_length * front_length), dims.head_width * 0.96),
    )


def generate_vector_attachments(
    request: CharacterBuilderRequest,
    rig: RigDefinition,
    region: RegenerationRegion = "all",
) -> tuple[AttachmentDefinition, ...]:
    dims = _dimensions(request)
    skin = _style_fill(request, request.palette.skin)
    hair = _style_fill(request, request.palette.hair)
    top = _style_fill(request, request.palette.top)
    bottom = _style_fill(request, request.palette.bottom)
    shoes = _style_fill(request, request.palette.shoes)
    accent = _style_fill(request, request.palette.accent)
    ink = "#1f2328" if request.style != "silhouette" else "#222222"
    attachments: list[AttachmentDefinition] = []

    include_all = region == "all"
    if include_all:
        attachments.extend(
            [
                _primitive(
                    "part_neck",
                    "neck",
                    "capsule",
                    (dims.neck_length, dims.arm_thickness * 0.72),
                    skin,
                    z_index=0,
                ),
                _primitive(
                    "part_torso",
                    "chest",
                    "rectangle",
                    (dims.chest_length * 1.05, dims.shoulder_width),
                    top,
                    z_index=4,
                    opacity=_style_opacity(request, 0.96),
                ),
                _primitive(
                    "part_waist",
                    "spine_lower",
                    "rectangle",
                    (dims.torso_lower + dims.torso_upper * 0.4, dims.waist_width),
                    top,
                    z_index=3,
                    opacity=_style_opacity(request, 0.94),
                ),
                _primitive(
                    "part_pelvis",
                    "hips",
                    "rectangle",
                    (dims.hip_length * 1.08, dims.pelvis_width),
                    bottom,
                    z_index=2,
                    opacity=_style_opacity(request, 0.96),
                ),
                _primitive(
                    "part_head",
                    "head",
                    "ellipse",
                    (dims.head_length * 0.92, dims.head_width),
                    skin,
                    position=(dims.head_length * 0.02, 0.0),
                    z_index=8,
                ),
            ]
        )

        for side in SIDES:
            factor = _side_factor(side, dims.side_asymmetry)
            back_z = -3 if side == "r" else 5
            attachments.extend(
                [
                    _primitive(
                        f"part_upper_arm_{side}",
                        f"upper_arm_{side}",
                        "capsule",
                        (dims.upper_arm_length * factor, dims.arm_thickness),
                        top if request.top != "shirt" else skin,
                        z_index=back_z,
                        opacity=_style_opacity(request),
                    ),
                    _primitive(
                        f"part_forearm_{side}",
                        f"forearm_{side}",
                        "capsule",
                        (dims.forearm_length * factor, dims.arm_thickness * 0.88),
                        skin,
                        z_index=back_z,
                    ),
                    _primitive(
                        f"part_hand_{side}",
                        f"hand_{side}",
                        "ellipse",
                        (dims.hand_length * factor, dims.arm_thickness * 1.02),
                        skin,
                        z_index=back_z + 1,
                    ),
                    _primitive(
                        f"part_thigh_{side}",
                        f"thigh_{side}",
                        "capsule",
                        (dims.thigh_length * factor, dims.leg_thickness),
                        bottom,
                        z_index=-1 if side == "r" else 1,
                        opacity=_style_opacity(request),
                    ),
                    _primitive(
                        f"part_shin_{side}",
                        f"shin_{side}",
                        "capsule",
                        (dims.shin_length * factor, dims.leg_thickness * 0.86),
                        bottom if request.bottom != "shorts" else skin,
                        z_index=-1 if side == "r" else 1,
                        opacity=_style_opacity(request),
                    ),
                    _primitive(
                        f"part_foot_{side}",
                        f"foot_{side}",
                        "capsule",
                        (dims.foot_length * factor, dims.leg_thickness * 0.72),
                        shoes,
                        z_index=3,
                    ),
                    _primitive(
                        f"part_toe_{side}",
                        f"toe_{side}",
                        "capsule",
                        (dims.toe_length * factor, dims.leg_thickness * 0.58),
                        shoes,
                        z_index=3,
                    ),
                ]
            )
            if request.top in {"sweater", "jacket"}:
                attachments.append(
                    _mesh_attachment(
                        f"mesh_sleeve_{side}",
                        f"upper_arm_{side}",
                        (f"upper_arm_{side}", f"forearm_{side}"),
                        rig,
                        dims.upper_arm_length * factor,
                        dims.forearm_length * factor,
                        dims.arm_thickness * (1.16 if request.top == "jacket" else 1.02),
                        top,
                        z_index=back_z + 2,
                        opacity=_style_opacity(request, 0.9),
                        secondary_motion=0.18 if request.top == "jacket" else 0.08,
                    )
                )
            if request.bottom == "trousers":
                attachments.append(
                    _mesh_attachment(
                        f"mesh_trouser_{side}",
                        f"thigh_{side}",
                        (f"thigh_{side}", f"shin_{side}"),
                        rig,
                        dims.thigh_length * factor,
                        dims.shin_length * factor,
                        dims.leg_thickness * 1.04,
                        bottom,
                        z_index=0 if side == "r" else 2,
                        opacity=_style_opacity(request, 0.88),
                        secondary_motion=0.05,
                    )
                )

    if region in {"all", "hair"} and request.hair_style != "bald":
        back_size, front_size = _hair_sizes(request.hair_style, dims)
        attachments.extend(
            [
                _primitive(
                    "part_hair_back",
                    "head",
                    "ellipse",
                    back_size,
                    hair,
                    position=(-dims.head_length * 0.08, 0.0),
                    z_index=6,
                    opacity=_style_opacity(request),
                ),
                _primitive(
                    "part_hair_front",
                    "head",
                    "ellipse" if request.hair_style in {"curly", "coily"} else "rectangle",
                    front_size,
                    hair,
                    position=(dims.head_length * 0.45, 0.0),
                    z_index=10,
                    opacity=_style_opacity(request),
                ),
            ]
        )

    if region in {"all", "face"}:
        eye_size = dims.head_width * 0.105
        attachments.extend(
            [
                _primitive("part_eye_l", "eye_l", "ellipse", (eye_size, eye_size), ink, z_index=12),
                _primitive("part_eye_r", "eye_r", "ellipse", (eye_size, eye_size), ink, z_index=12),
                _primitive(
                    "part_brow_l",
                    "eye_l",
                    "rectangle",
                    (eye_size * 1.4, eye_size * 0.28),
                    hair,
                    position=(0.0, eye_size * 1.15),
                    z_index=13,
                ),
                _primitive(
                    "part_brow_r",
                    "eye_r",
                    "rectangle",
                    (eye_size * 1.4, eye_size * 0.28),
                    hair,
                    position=(0.0, eye_size * 1.15),
                    z_index=13,
                ),
                _primitive(
                    "part_nose",
                    "head",
                    "capsule",
                    (dims.head_length * 0.12, eye_size * 0.8),
                    "#8b5e42" if request.style != "silhouette" else ink,
                    position=(dims.head_length * 0.58, 0.0),
                    z_index=13,
                    opacity=0.8,
                ),
                _primitive(
                    "part_mouth",
                    "head",
                    "rectangle",
                    (dims.head_length * 0.14, eye_size * 0.25),
                    "#8b1e32" if request.style != "silhouette" else ink,
                    position=(dims.head_length * 0.72, 0.0),
                    z_index=13,
                ),
            ]
        )

    if region in {"all", "clothing"}:
        if request.outerwear != "none":
            attachments.append(
                _primitive(
                    "part_outerwear",
                    "chest",
                    "rectangle",
                    (
                        dims.chest_length * (1.12 if request.outerwear == "coat" else 0.98),
                        dims.shoulder_width * 1.08,
                    ),
                    accent,
                    z_index=7,
                    opacity=_style_opacity(request, 0.78),
                )
            )
            for side in SIDES:
                factor = _side_factor(side, dims.side_asymmetry)
                attachments.append(
                    _mesh_attachment(
                        f"mesh_outer_sleeve_{side}",
                        f"upper_arm_{side}",
                        (f"upper_arm_{side}", f"forearm_{side}"),
                        rig,
                        dims.upper_arm_length * factor,
                        dims.forearm_length * factor,
                        dims.arm_thickness * 1.32,
                        accent,
                        z_index=8,
                        opacity=_style_opacity(request, 0.72),
                        secondary_motion=0.22 if request.outerwear == "coat" else 0.12,
                    )
                )
        if request.bottom == "skirt":
            attachments.append(
                _primitive(
                    "part_skirt",
                    "hips",
                    "rectangle",
                    (dims.hip_length * 1.42, dims.pelvis_width * 1.22),
                    bottom,
                    z_index=6,
                    opacity=_style_opacity(request, 0.94),
                )
            )
            attachments.append(
                _mesh_attachment(
                    "mesh_skirt_panel",
                    "hips",
                    ("hips", "spine_lower"),
                    rig,
                    dims.hip_length * 0.82,
                    dims.torso_lower * 0.42,
                    dims.pelvis_width * 1.28,
                    bottom,
                    z_index=7,
                    opacity=_style_opacity(request, 0.72),
                    secondary_motion=0.35,
                )
            )
        if request.footwear in {"boots", "sneakers"}:
            for side in SIDES:
                factor = _side_factor(side, dims.side_asymmetry)
                attachments.append(
                    _primitive(
                        f"part_{request.footwear}_{side}",
                        f"foot_{side}",
                        "rectangle" if request.footwear == "boots" else "capsule",
                        (dims.foot_length * factor * 0.82, dims.leg_thickness * 0.84),
                        accent if request.footwear == "sneakers" else shoes,
                        z_index=4,
                    )
                )

    return tuple(attachments)


def _attachment_bounds_ok(attachment: AttachmentDefinition, margin_ratio: float = 0.25) -> bool:
    primitive = attachment.primitive
    if primitive is None:
        return True
    width, height = primitive.size
    margin_x = max(width * margin_ratio, 0.02)
    margin_y = max(height * margin_ratio, 0.02)
    pivot_x, pivot_y = attachment.pivot
    return (
        -margin_x <= pivot_x <= width + margin_x
        and -height / 2 - margin_y <= pivot_y <= height / 2 + margin_y
    )


def diagnose_generated_character(
    character: CharacterDefinition,
    normalized_request: CharacterBuilderRequest,
) -> tuple[BuilderDiagnostic, ...]:
    diagnostics: list[BuilderDiagnostic] = []
    dims = _dimensions(normalized_request)

    for issue in validate_character(character):
        diagnostics.append(
            _diagnostic(
                issue.code,
                "error",
                issue.message,
                issue.path,
            )
        )

    for index, bone in enumerate(character.rig.bones):
        if bone.length < 0.0:
            diagnostics.append(
                _diagnostic(
                    "BUILDER_NEGATIVE_BONE_LENGTH",
                    "error",
                    f"bone {bone.id!r} has a negative length",
                    f"rig.bones[{index}].length",
                    bone.length,
                )
            )
        if bone.id != "root" and bone.length <= 0.0:
            diagnostics.append(
                _diagnostic(
                    "BUILDER_ZERO_BONE_LENGTH",
                    "error",
                    f"bone {bone.id!r} has a non-positive length",
                    f"rig.bones[{index}].length",
                    bone.length,
                )
            )

    for index, attachment in enumerate(character.attachments):
        primitive = attachment.primitive
        if primitive is not None:
            width, height = primitive.size
            if width <= 0.0 or height <= 0.0:
                diagnostics.append(
                    _diagnostic(
                        "BUILDER_NONPOSITIVE_PART_DIMENSION",
                        "error",
                        f"attachment {attachment.id!r} has a non-positive primitive size",
                        f"attachments[{index}].primitive.size",
                    )
                )
        mesh = attachment.mesh
        if mesh is not None:
            for vertex_index, vertex_weights in enumerate(mesh.weights):
                total = sum(weight.weight for weight in vertex_weights.weights)
                if abs(total - 1.0) > 1e-6:
                    diagnostics.append(
                        _diagnostic(
                            "BUILDER_MESH_WEIGHT_SUM",
                            "error",
                            f"attachment {attachment.id!r} vertex {vertex_index} weights "
                            "do not sum to 1",
                            f"attachments[{index}].mesh.weights[{vertex_index}]",
                            total,
                            1.0,
                        )
                    )
        if not _attachment_bounds_ok(attachment):
            diagnostics.append(
                _diagnostic(
                    "BUILDER_PIVOT_OUT_OF_BOUNDS",
                    "warning",
                    f"attachment {attachment.id!r} has a pivot outside its expanded bounds",
                    f"attachments[{index}].pivot",
                )
            )

    bones = {bone.id: bone for bone in character.rig.bones}
    for base_name in ("upper_arm", "forearm", "thigh", "shin", "foot", "toe"):
        left = bones[f"{base_name}_l"].length
        right = bones[f"{base_name}_r"].length
        max_side = max(left, right, 1e-6)
        relative = abs(left - right) / max_side
        if relative > dims.side_asymmetry + 0.002:
            diagnostics.append(
                _diagnostic(
                    "BUILDER_BILATERAL_MISMATCH",
                    "warning",
                    f"{base_name} left/right lengths exceed the requested controlled asymmetry",
                    f"rig.bones.{base_name}",
                    relative,
                    dims.side_asymmetry,
                )
            )

    if (
        dims.shoulder_width < dims.pelvis_width * 0.58
        or dims.pelvis_width < dims.waist_width * 0.58
    ):
        diagnostics.append(
            _diagnostic(
                "BUILDER_EXTREME_OVERLAP_RISK",
                "warning",
                "body width relationships are near the edge of the supported procedural silhouette",
                "proportions",
            )
        )

    return tuple(diagnostics)


def build_procedural_character(request: CharacterBuilderRequest) -> CharacterBuilderResult:
    normalized, normalization_diagnostics = normalize_character_request(request)
    rig = generate_canonical_human_rig(normalized)
    character = CharacterDefinition(
        id=_character_id(normalized),
        name=normalized.name,
        rig=rig,
        attachments=generate_vector_attachments(normalized, rig),
    )
    constraints = generate_rig_constraints(rig)
    diagnostics = (
        *normalization_diagnostics,
        *diagnose_generated_character(character, normalized),
    )
    return CharacterBuilderResult(
        normalized_request=normalized,
        character=character,
        constraints=constraints,
        diagnostics=diagnostics,
    )


def primitive_attachment_svg(attachment: AttachmentDefinition) -> str:
    primitive = attachment.primitive
    if primitive is None:
        return ""
    width, height = primitive.size
    fill = escape(primitive.fill)
    opacity = f"{primitive.opacity:.3f}".rstrip("0").rstrip(".")
    if primitive.shape == "ellipse":
        body = (
            f'<ellipse cx="{width / 2:.6f}" cy="0" rx="{width / 2:.6f}" '
            f'ry="{height / 2:.6f}" fill="{fill}" opacity="{opacity}" />'
        )
    elif primitive.shape == "rectangle":
        body = (
            f'<rect x="0" y="{-height / 2:.6f}" width="{width:.6f}" '
            f'height="{height:.6f}" fill="{fill}" opacity="{opacity}" />'
        )
    else:
        radius = height / 2.0
        body = (
            f'<rect x="0" y="{-radius:.6f}" width="{width:.6f}" '
            f'height="{height:.6f}" rx="{radius:.6f}" ry="{radius:.6f}" '
            f'fill="{fill}" opacity="{opacity}" />'
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" data-part-id="{escape(attachment.id)}" '
        f'viewBox="0 {-height / 2:.6f} {width:.6f} {height:.6f}">{body}</svg>'
    )


def combined_character_svg(character: CharacterDefinition) -> str:
    worlds = compute_world_transforms(character.rig)
    parts: list[str] = []
    for attachment in sorted(character.attachments, key=lambda part: (part.z_index, part.id)):
        primitive = attachment.primitive
        bone_world = worlds.get(attachment.bone_id)
        if primitive is None or bone_world is None or not attachment.visible:
            continue
        local = attachment.transform.to_transform2d().to_affine()
        matrix = bone_world.multiply(local)
        width, height = primitive.size
        shape_svg = primitive_attachment_svg(attachment)
        start = shape_svg.find(">")
        end = shape_svg.rfind("</svg>")
        body = shape_svg[start + 1 : end]
        parts.append(
            "<g "
            f'data-part-id="{escape(attachment.id)}" '
            f'transform="matrix({matrix.a:.6f} {matrix.b:.6f} {matrix.c:.6f} '
            f"{matrix.d:.6f} {matrix.tx:.6f} {matrix.ty:.6f}) "
            f'translate({-attachment.pivot[0]:.6f} {-attachment.pivot[1]:.6f})" '
            f'data-size="{width:.6f},{height:.6f}">{body}</g>'
        )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'data-character-id="{escape(character.id)}" viewBox="-2 -0.5 4 4.5">'
        + "".join(parts)
        + "</svg>"
    )


def _palette(
    skin: str,
    hair: str,
    top: str,
    bottom: str,
    shoes: str,
    accent: str,
) -> CharacterPalette:
    return CharacterPalette(
        skin=skin,
        hair=hair,
        top=top,
        bottom=bottom,
        shoes=shoes,
        accent=accent,
    )


PRESET_REQUESTS: tuple[CharacterBuilderRequest, ...] = (
    CharacterBuilderRequest(
        name="Mira Vector",
        presentation="feminine",
        age_category="adult",
        height="average",
        build="slender",
        proportions=CharacterProportions(hip_width=1.08, waist_width=0.88, arm_length=1.04),
        palette=_palette("#b87952", "#2d1d16", "#2f6f73", "#293c62", "#2b2b2b", "#f2c94c"),
        hair_style="bob",
        face_shape="heart",
        top="shirt",
        bottom="trousers",
        footwear="sneakers",
        style="flat_vector",
    ),
    CharacterBuilderRequest(
        name="Jon Cutout",
        presentation="masculine",
        age_category="adult",
        height="tall",
        build="broad",
        proportions=CharacterProportions(shoulder_width=1.14, hip_width=0.94, leg_length=1.08),
        palette=_palette("#9f6b45", "#1f1a17", "#7b3443", "#263238", "#111111", "#d9a441"),
        hair_style="short",
        face_shape="square",
        top="jacket",
        bottom="trousers",
        footwear="boots",
        style="paper_cutout",
    ),
    CharacterBuilderRequest(
        name="Noor Graphic",
        presentation="neutral",
        age_category="teen",
        height="short",
        build="average",
        proportions=CharacterProportions(head_size=1.08, arm_length=0.94, torso_length=0.94),
        palette=_palette("#d6a06f", "#4b2f21", "#5b8c5a", "#3a4a6b", "#303030", "#ffffff"),
        hair_style="curly",
        face_shape="round",
        top="sweater",
        bottom="shorts",
        footwear="sneakers",
        style="graphic_novel",
    ),
    CharacterBuilderRequest(
        name="Ari Silhouette",
        presentation="neutral",
        age_category="adult",
        height="tall",
        build="slender",
        proportions=CharacterProportions(leg_length=1.16, shoulder_width=0.92),
        palette=CharacterPalette(),
        hair_style="long",
        face_shape="long",
        top="shirt",
        bottom="skirt",
        footwear="shoes",
        style="silhouette",
    ),
    CharacterBuilderRequest(
        name="Lena Cartoon",
        presentation="feminine",
        age_category="older_adult",
        height="short",
        build="sturdy",
        proportions=CharacterProportions(head_size=1.05, torso_length=1.08, leg_length=0.9),
        palette=_palette("#c98764", "#bfc4c7", "#7952b3", "#4a5568", "#202020", "#edf2f7"),
        hair_style="coily",
        face_shape="oval",
        top="jacket",
        bottom="trousers",
        footwear="shoes",
        outerwear="vest",
        style="cartoon",
    ),
    CharacterBuilderRequest(
        name="Kai Flat",
        presentation="masculine",
        age_category="teen",
        height="average",
        build="slender",
        proportions=CharacterProportions(arm_length=1.12, shoulder_width=1.02, asymmetry=0.02),
        palette=_palette("#e0b38f", "#161616", "#1b998b", "#2d3047", "#3d3d3d", "#fffd82"),
        hair_style="short",
        face_shape="oval",
        top="tshirt",
        bottom="trousers",
        footwear="sneakers",
        style="flat_vector",
    ),
    CharacterBuilderRequest(
        name="Sana Paper",
        presentation="feminine",
        age_category="adult",
        height="short",
        build="average",
        proportions=CharacterProportions(hip_width=1.18, waist_width=0.82, head_size=0.96),
        palette=_palette("#8d5d42", "#25180f", "#b56576", "#6d597a", "#1c1c1c", "#eaac8b"),
        hair_style="long",
        face_shape="heart",
        top="shirt",
        bottom="skirt",
        footwear="shoes",
        outerwear="coat",
        style="paper_cutout",
    ),
    CharacterBuilderRequest(
        name="Owen Novel",
        presentation="masculine",
        age_category="older_adult",
        height="average",
        build="sturdy",
        proportions=CharacterProportions(shoulder_width=1.18, torso_length=1.1, head_size=0.98),
        palette=_palette("#bc8a5f", "#dddddd", "#364958", "#55828b", "#212529", "#c9e4ca"),
        hair_style="short",
        face_shape="square",
        top="sweater",
        bottom="trousers",
        footwear="boots",
        style="graphic_novel",
    ),
    CharacterBuilderRequest(
        name="Paz Child",
        presentation="neutral",
        age_category="child",
        height="short",
        build="average",
        proportions=CharacterProportions(head_size=1.14, leg_length=0.86, arm_length=0.88),
        palette=_palette("#d99f7a", "#6b3f2a", "#e76f51", "#2a9d8f", "#264653", "#f4a261"),
        hair_style="curly",
        face_shape="round",
        top="tshirt",
        bottom="shorts",
        footwear="sneakers",
        style="cartoon",
    ),
    CharacterBuilderRequest(
        name="Rue Neutral",
        presentation="neutral",
        age_category="adult",
        height="average",
        build="broad",
        proportions=CharacterProportions(
            shoulder_width=1.04,
            hip_width=1.06,
            torso_length=0.92,
            asymmetry=0.035,
        ),
        palette=_palette("#6f4b3e", "#101010", "#577590", "#43aa8b", "#2f2f2f", "#f94144"),
        hair_style="bald",
        face_shape="oval",
        top="jacket",
        bottom="trousers",
        footwear="boots",
        style="flat_vector",
    ),
)
