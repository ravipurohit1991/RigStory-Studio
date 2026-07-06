"""Regenerate shared sample fixtures and math golden vectors.

Run from ``backend/``::

    python scripts/generate_fixtures.py

Output is deterministic canonical JSON so regeneration produces meaningful
diffs. Valid fixtures are validated before writing; the script fails rather
than emit a broken sample. Both the backend pytest suite and the frontend
vitest suite consume these files, which is what pins the two implementations
to identical numerical behavior.
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.domain.blueprint import (  # noqa: E402
    CANNED_BLUEPRINT,
    blueprint_to_builder_request,
)
from app.domain.canonical import (  # noqa: E402
    JsonValue,
    canonical_json_dumps,
    canonical_json_pretty,
)
from app.domain.character import AttachmentDefinition, CharacterDefinition  # noqa: E402
from app.domain.character_builder import build_procedural_character  # noqa: E402
from app.domain.clip import (  # noqa: E402
    AnimationClip,
    BoneRotationTrack,
    ClipMarker,
    RootTranslationTrack,
    ScalarKeyframe,
    VectorKeyframe,
)
from app.domain.common import TransformSpec  # noqa: E402
from app.domain.errors import DomainValidationError  # noqa: E402
from app.domain.generation import (  # noqa: E402
    GenerationAttempt,
    GenerationOptionsRecord,
    GenerationRecord,
)
from app.domain.math2d.affine import Affine2  # noqa: E402
from app.domain.math2d.angles import lerp_angle_deg, normalize_deg, shortest_delta_deg  # noqa: E402
from app.domain.math2d.bezier import cubic_scalar  # noqa: E402
from app.domain.math2d.rng import SeededRng, seed_from_string  # noqa: E402
from app.domain.math2d.vec2 import Vec2  # noqa: E402
from app.domain.project import (  # noqa: E402
    ProjectDocument,
    ProjectInfo,
    validate_project_document,
)
from app.domain.rig import (  # noqa: E402
    BoneDefinition,
    JointLimit,
    RigDefinition,
    compute_bone_endpoints,
)
from app.domain.scene import (  # noqa: E402
    ActorInstance,
    Affordance,
    Anchor,
    BoxCollider,
    SceneDefinition,
    SceneObject,
)
from app.domain.versioning import ENGINE_VERSION, PROJECT_SCHEMA_VERSION  # noqa: E402

SAMPLES = REPO_ROOT / "samples"


def _transform(
    x: float, y: float, rotation_deg: float = 0.0, scale: tuple[float, float] = (1.0, 1.0)
) -> TransformSpec:
    return TransformSpec(position=(x, y), rotation_deg=rotation_deg, scale=scale)


def build_two_bone_rig() -> RigDefinition:
    return RigDefinition(
        id="rig_two_bone",
        name="Two-bone test rig",
        bones=(
            BoneDefinition(
                id="bone_a",
                setup_transform=_transform(0.0, 0.0, 30.0),
                length=10.0,
            ),
            BoneDefinition(
                id="bone_b",
                parent_id="bone_a",
                setup_transform=_transform(10.0, 0.0, 40.0),
                length=5.0,
            ),
        ),
    )


def _mirrored_limb_bones() -> list[BoneDefinition]:
    """Arm and leg chains for both sides with mirrored transforms."""
    bones: list[BoneDefinition] = []
    for side, sign in (("l", 1.0), ("r", -1.0)):
        bones.extend(
            [
                BoneDefinition(
                    id=f"clavicle_{side}",
                    parent_id="chest",
                    setup_transform=_transform(0.30, sign * 0.06, sign * 95.0),
                    length=0.25,
                    tags=("arm", side),
                ),
                BoneDefinition(
                    id=f"upper_arm_{side}",
                    parent_id=f"clavicle_{side}",
                    setup_transform=_transform(0.25, 0.0, sign * 78.0),
                    length=0.55,
                    joint_limit=JointLimit(min_rotation_deg=-170.0, max_rotation_deg=170.0),
                    tags=("arm", side, "ik_chain"),
                ),
                BoneDefinition(
                    id=f"forearm_{side}",
                    parent_id=f"upper_arm_{side}",
                    setup_transform=_transform(0.55, 0.0, sign * -4.0),
                    length=0.50,
                    joint_limit=(
                        JointLimit(min_rotation_deg=-150.0, max_rotation_deg=5.0)
                        if side == "l"
                        else JointLimit(min_rotation_deg=-5.0, max_rotation_deg=150.0)
                    ),
                    tags=("arm", side, "ik_chain"),
                ),
                BoneDefinition(
                    id=f"hand_{side}",
                    parent_id=f"forearm_{side}",
                    setup_transform=_transform(0.50, 0.0, 0.0),
                    length=0.20,
                    tags=("arm", side),
                ),
                BoneDefinition(
                    id=f"thigh_{side}",
                    parent_id="hips",
                    setup_transform=_transform(-0.05, sign * 0.11, 180.0),
                    length=0.85,
                    joint_limit=JointLimit(min_rotation_deg=-120.0, max_rotation_deg=120.0),
                    tags=("leg", side, "ik_chain"),
                ),
                BoneDefinition(
                    id=f"shin_{side}",
                    parent_id=f"thigh_{side}",
                    setup_transform=_transform(0.85, 0.0, 0.0),
                    length=0.75,
                    joint_limit=(
                        JointLimit(min_rotation_deg=-5.0, max_rotation_deg=150.0)
                        if side == "l"
                        else JointLimit(min_rotation_deg=-150.0, max_rotation_deg=5.0)
                    ),
                    tags=("leg", side, "ik_chain"),
                ),
                BoneDefinition(
                    id=f"foot_{side}",
                    parent_id=f"shin_{side}",
                    setup_transform=_transform(0.75, 0.0, 90.0),
                    length=0.30,
                    tags=("leg", side),
                ),
                BoneDefinition(
                    id=f"toe_{side}",
                    parent_id=f"foot_{side}",
                    setup_transform=_transform(0.30, 0.0, 0.0),
                    length=0.12,
                    tags=("leg", side),
                ),
            ]
        )
    return bones


def build_biped_rig(rig_id: str) -> RigDefinition:
    """Canonical human biped (spec section 11) at roughly 3.45 scene units tall.

    The torso chain points up: ``hips`` rotates +90 degrees so descendant
    bones extend along world +Y with zero local rotation.
    """
    core = [
        BoneDefinition(id="root", setup_transform=_transform(0.0, 0.0), length=0.0),
        BoneDefinition(
            id="hips",
            parent_id="root",
            setup_transform=_transform(0.0, 1.70, 90.0),
            length=0.20,
            tags=("core",),
        ),
        BoneDefinition(
            id="spine_lower",
            parent_id="hips",
            setup_transform=_transform(0.20, 0.0, 0.0),
            length=0.30,
            joint_limit=JointLimit(min_rotation_deg=-30.0, max_rotation_deg=30.0),
            tags=("core",),
        ),
        BoneDefinition(
            id="spine_upper",
            parent_id="spine_lower",
            setup_transform=_transform(0.30, 0.0, 0.0),
            length=0.30,
            joint_limit=JointLimit(min_rotation_deg=-30.0, max_rotation_deg=30.0),
            tags=("core",),
        ),
        BoneDefinition(
            id="chest",
            parent_id="spine_upper",
            setup_transform=_transform(0.30, 0.0, 0.0),
            length=0.35,
            tags=("core",),
        ),
        BoneDefinition(
            id="neck",
            parent_id="chest",
            setup_transform=_transform(0.35, 0.0, 0.0),
            length=0.15,
            joint_limit=JointLimit(min_rotation_deg=-40.0, max_rotation_deg=40.0),
            tags=("core",),
        ),
        BoneDefinition(
            id="head",
            parent_id="neck",
            setup_transform=_transform(0.15, 0.0, 0.0),
            length=0.45,
            tags=("core",),
        ),
        BoneDefinition(
            id="eye_l",
            parent_id="head",
            setup_transform=_transform(0.25, 0.09, 0.0),
            length=0.05,
            tags=("face", "l"),
        ),
        BoneDefinition(
            id="eye_r",
            parent_id="head",
            setup_transform=_transform(0.25, -0.09, 0.0),
            length=0.05,
            tags=("face", "r"),
        ),
    ]
    return RigDefinition(
        id=rig_id, name="Canonical biped", bones=tuple(core + _mirrored_limb_bones())
    )


def build_biped_character(character_id: str, name: str, rig_id: str) -> CharacterDefinition:
    attachments = (
        AttachmentDefinition(
            id="part_pelvis",
            bone_id="hips",
            kind="primitive",
            transform=_transform(0.10, 0.0),
            z_index=0,
        ),
        AttachmentDefinition(
            id="part_torso",
            bone_id="chest",
            kind="primitive",
            transform=_transform(0.17, 0.0),
            z_index=1,
        ),
        AttachmentDefinition(
            id="part_head",
            bone_id="head",
            kind="primitive",
            transform=_transform(0.22, 0.0),
            z_index=2,
        ),
        AttachmentDefinition(
            id="part_arm_upper_l",
            bone_id="upper_arm_l",
            kind="primitive",
            transform=_transform(0.27, 0.0),
            z_index=3,
        ),
        AttachmentDefinition(
            id="part_arm_upper_r",
            bone_id="upper_arm_r",
            kind="primitive",
            transform=_transform(0.27, 0.0),
            z_index=-3,
        ),
        AttachmentDefinition(
            id="part_leg_upper_l",
            bone_id="thigh_l",
            kind="primitive",
            transform=_transform(0.42, 0.0),
            z_index=2,
        ),
        AttachmentDefinition(
            id="part_leg_upper_r",
            bone_id="thigh_r",
            kind="primitive",
            transform=_transform(0.42, 0.0),
            z_index=-2,
        ),
    )
    return CharacterDefinition(
        id=character_id,
        name=name,
        rig=build_biped_rig(rig_id),
        attachments=attachments,
    )


def build_floor() -> SceneObject:
    return SceneObject(
        id="floor_main",
        name="Floor",
        kind="floor",
        bounds=(-10.0, -1.0, 10.0, 0.0),
        colliders=(BoxCollider(center=(0.0, -0.5), size=(20.0, 1.0)),),
        collision_layer="ground",
    )


def build_chair() -> SceneObject:
    return SceneObject(
        id="chair_1",
        name="Chair",
        kind="chair",
        transform=_transform(2.7, 0.0),
        bounds=(2.0, 0.0, 3.4, 2.2),
        colliders=(BoxCollider(center=(0.0, 1.1), size=(1.4, 2.2)),),
        anchors=(
            Anchor(id="seat", position=(0.0, 1.05)),
            Anchor(id="back", position=(0.5, 1.75)),
        ),
        affordances=(
            Affordance(type="sit", anchor_id="seat"),
            Affordance(type="look_at"),
            Affordance(type="avoid"),
        ),
    )


def build_scene_empty() -> SceneDefinition:
    return SceneDefinition(
        id="scene_empty",
        name="Empty scene",
        world_bounds=(-10.0, -1.0, 10.0, 8.0),
    )


def build_scene_one_character() -> SceneDefinition:
    return SceneDefinition(
        id="scene_room",
        name="Room with chair",
        world_bounds=(-10.0, -1.0, 10.0, 8.0),
        actors=(
            ActorInstance(
                id="actor_mira",
                character_id="char_biped_alpha",
                display_name="Mira",
                root_transform=_transform(-2.0, 0.0),
                facing="right",
            ),
        ),
        objects=(build_floor(), build_chair()),
    )


def build_scene_two_characters() -> SceneDefinition:
    return SceneDefinition(
        id="scene_meeting",
        name="Meeting",
        world_bounds=(-10.0, -1.0, 10.0, 8.0),
        actors=(
            ActorInstance(
                id="actor_mira",
                character_id="char_biped_alpha",
                display_name="Mira",
                root_transform=_transform(-2.0, 0.0),
                facing="right",
            ),
            ActorInstance(
                id="actor_jon",
                character_id="char_biped_beta",
                display_name="Jon",
                root_transform=_transform(2.0, 0.0),
                facing="left",
            ),
        ),
        objects=(build_floor(),),
    )


def build_wave_clip() -> AnimationClip:
    return AnimationClip(
        id="clip_wave",
        scene_id="scene_room",
        name="Seated wave",
        duration=1.2,
        tracks=(
            BoneRotationTrack(
                id="track_wave_forearm_r",
                actor_id="actor_mira",
                bone_id="forearm_r",
                keyframes=(
                    ScalarKeyframe(id="key_wave_0", time=0.0, value=4.0),
                    ScalarKeyframe(id="key_wave_1", time=0.6, value=60.0, interpolation="cubic"),
                    ScalarKeyframe(id="key_wave_2", time=1.2, value=4.0),
                ),
            ),
            RootTranslationTrack(
                id="track_root_mira",
                actor_id="actor_mira",
                keyframes=(
                    VectorKeyframe(id="key_root_0", time=0.0, value=(-2.0, 0.0)),
                    VectorKeyframe(id="key_root_1", time=1.2, value=(-2.0, 0.0)),
                ),
            ),
        ),
        markers=(ClipMarker(name="wave peak", time=0.6, kind="marker"),),
    )


def build_biped_project() -> ProjectDocument:
    return ProjectDocument(
        format="rigstory-project",
        schema_version=str(PROJECT_SCHEMA_VERSION),
        engine_version=str(ENGINE_VERSION),
        project=ProjectInfo(id="project_biped_demo", name="Biped Demo"),
        characters=(
            build_biped_character("char_biped_alpha", "Mira", "rig_biped_alpha"),
            build_biped_character("char_biped_beta", "Jon", "rig_biped_beta"),
        ),
        scenes=(
            build_scene_empty(),
            build_scene_one_character(),
            build_scene_two_characters(),
        ),
        clips=(build_wave_clip(),),
    )


def build_generated_project() -> ProjectDocument:
    """A project produced by the deterministic mapping of a canned blueprint.

    The blueprint stands in for a validated Ollama response; the character and
    rig are produced by the deterministic builder, not the model. The generation
    record uses fixed identifiers and timestamp so the sample stays byte-stable.
    """
    mapping = blueprint_to_builder_request(CANNED_BLUEPRINT)
    built = build_procedural_character(mapping.request)
    character = built.character.model_copy(update={"id": "char_generated_demo"})
    record = GenerationRecord(
        id="gen_demo0001",
        created_at="2026-07-04T00:00:00Z",
        character_id=character.id,
        model_name="example-planner-model",
        prompt_ids=("character_blueprint.system.v1", "character_blueprint.user.v1"),
        options=GenerationOptionsRecord(temperature=0.1, keep_alive="10m", timeout_seconds=60.0),
        status="succeeded",
        outcome_detail="Validated on the first attempt.",
        attempts=(
            GenerationAttempt(
                index=0,
                kind="initial",
                valid=True,
                raw_response=canonical_json_dumps(CANNED_BLUEPRINT.model_dump(mode="json")),
            ),
        ),
        blueprint=CANNED_BLUEPRINT,
        builder_diagnostics=built.diagnostics,
        warnings=mapping.warnings,
    )
    return ProjectDocument(
        format="rigstory-project",
        schema_version=str(PROJECT_SCHEMA_VERSION),
        engine_version=str(ENGINE_VERSION),
        project=ProjectInfo(id="project_generated_demo", name="Generated Character Demo"),
        characters=(character,),
        generation_records=(record,),
    )


def build_empty_project() -> ProjectDocument:
    return ProjectDocument(
        format="rigstory-project",
        schema_version=str(PROJECT_SCHEMA_VERSION),
        engine_version=str(ENGINE_VERSION),
        project=ProjectInfo(id="project_empty_demo", name="Empty Project"),
    )


def build_invalid_fixtures() -> dict[str, JsonValue]:
    """Raw documents that must be rejected; keys are file names."""

    def bone(bone_id: str, parent: str | None) -> JsonValue:
        result: dict[str, JsonValue] = {
            "id": bone_id,
            "parent_id": parent,
            "setup_transform": {
                "position": [0.0, 0.0],
                "rotation_deg": 0.0,
                "scale": [1.0, 1.0],
            },
            "length": 1.0,
            "joint_limit": None,
            "tags": [],
        }
        return result

    valid_envelope: dict[str, JsonValue] = {
        "format": "rigstory-project",
        "schema_version": str(PROJECT_SCHEMA_VERSION),
        "engine_version": str(ENGINE_VERSION),
        "project": {"id": "project_invalid_demo", "name": "Invalid"},
        "characters": [],
        "scenes": [],
        "clips": [],
        "motion_plans": [],
        "generation_records": [],
        "asset_manifest": [],
    }

    three_actor_scene: JsonValue = {
        "id": "scene_crowd",
        "name": "Crowd",
        "world_bounds": [-10.0, -1.0, 10.0, 8.0],
        "ground_y": 0.0,
        "actors": [
            {
                "id": f"actor_{name}",
                "character_id": "char_biped_alpha",
                "display_name": name.title(),
                "root_transform": {
                    "position": [0.0, 0.0],
                    "rotation_deg": 0.0,
                    "scale": [1.0, 1.0],
                },
                "facing": "right",
                "state": "standing",
            }
            for name in ("mira", "jon", "ada")
        ],
        "objects": [],
    }

    biped_character = build_biped_character(
        "char_biped_alpha", "Mira", "rig_biped_alpha"
    ).model_dump(mode="json")
    scene_room = build_scene_one_character().model_dump(mode="json")

    bad_refs_clip: JsonValue = {
        "id": "clip_bad_refs",
        "scene_id": "scene_room",
        "name": "Bad references",
        "duration": 1.0,
        "loop": False,
        "tracks": [
            {
                "type": "bone_rotation",
                "id": "track_bad_bone",
                "actor_id": "actor_mira",
                "bone_id": "wing_l",
                "keyframes": [
                    {"id": "key_bad_0", "time": 0.8, "value": 0.0, "interpolation": "linear"},
                    {"id": "key_bad_1", "time": 0.2, "value": 1.0, "interpolation": "linear"},
                ],
            }
        ],
        "events": [],
        "markers": [],
    }

    return {
        "rig-cycle.json": {
            "id": "rig_invalid_cycle",
            "name": "Cycle",
            "bones": [bone("root", None), bone("bone_b", "bone_c"), bone("bone_c", "bone_b")],
        },
        "rig-duplicate-bone-id.json": {
            "id": "rig_invalid_duplicate",
            "name": "Duplicate ids",
            "bones": [bone("root", None), bone("arm", "root"), bone("arm", "root")],
        },
        "rig-missing-parent.json": {
            "id": "rig_invalid_missing_parent",
            "name": "Missing parent",
            "bones": [bone("root", None), bone("arm", "ghost")],
        },
        "project-three-actors.rigstory.json": {
            **valid_envelope,
            "characters": [biped_character],
            "scenes": [three_actor_scene],
        },
        "project-future-version.rigstory.json": {
            **valid_envelope,
            "schema_version": "9.9.9",
        },
        "project-inverted-joint-limit.rigstory.json": {
            **valid_envelope,
            "characters": [
                {
                    "id": "char_invalid_limits",
                    "name": "Inverted limits",
                    "rig": {
                        "id": "rig_invalid_limits",
                        "name": "Inverted limits",
                        "bones": [
                            bone("root", None),
                            {
                                "id": "arm",
                                "parent_id": "root",
                                "setup_transform": {
                                    "position": [0.0, 0.0],
                                    "rotation_deg": 0.0,
                                    "scale": [1.0, 1.0],
                                },
                                "length": 1.0,
                                "joint_limit": {
                                    "min_rotation_deg": 30.0,
                                    "max_rotation_deg": -30.0,
                                    "soft_zone_deg": 0.0,
                                },
                                "tags": [],
                            },
                        ],
                    },
                    "attachments": [],
                }
            ],
        },
        "project-bad-refs.rigstory.json": {
            **valid_envelope,
            "characters": [biped_character],
            "scenes": [scene_room],
            "clips": [bad_refs_clip],
        },
    }


def build_math_goldens() -> JsonValue:
    """Numerical vectors pinning Python and TypeScript kernels together."""
    rng_cases: list[JsonValue] = []
    for seed in (1, 12345, 0xDEADBEEF):
        rng = SeededRng(seed)
        uints: list[JsonValue] = [rng.next_uint32() for _ in range(8)]
        rng_floats = SeededRng(seed)
        floats: list[JsonValue] = [rng_floats.next_float() for _ in range(4)]
        rng_cases.append({"seed": seed, "uint32": uints, "floats": floats})
    string_seeds: dict[str, JsonValue] = {
        text: seed_from_string(text) for text in ("", "a", "clip_01/actor_mira")
    }

    angle_cases: list[JsonValue] = [
        {"op": "normalize", "input": value, "expected": normalize_deg(value)}
        for value in (0.0, 180.0, -180.0, 540.0, -540.0, 359.0, 720.5)
    ]
    angle_cases.extend(
        {
            "op": "shortest_delta",
            "start": start,
            "end": end,
            "expected": shortest_delta_deg(start, end),
        }
        for start, end in ((359.0, 1.0), (10.0, 350.0), (-170.0, 170.0), (0.0, 180.0))
    )
    angle_cases.extend(
        {
            "op": "lerp",
            "start": start,
            "end": end,
            "t": t,
            "expected": lerp_angle_deg(start, end, t),
        }
        for start, end, t in ((359.0, 1.0, 0.5), (350.0, 20.0, 0.25), (90.0, -90.0, 0.5))
    )

    parent = Affine2.from_trs(Vec2(3.0, -2.0), 30.0, (2.0, 1.0))
    child = Affine2.from_trs(Vec2(1.5, 0.5), -45.0, (1.0, 3.0))
    composed = parent.multiply(child)
    point = Vec2(0.25, -1.75)
    composed_point = composed.apply_point(point)
    inverse_point = composed.inverse().apply_point(composed_point)
    affine_case: JsonValue = {
        "parent_trs": {"position": [3.0, -2.0], "rotation_deg": 30.0, "scale": [2.0, 1.0]},
        "child_trs": {"position": [1.5, 0.5], "rotation_deg": -45.0, "scale": [1.0, 3.0]},
        "point": [point.x, point.y],
        "composed_point": [composed_point.x, composed_point.y],
        "inverse_round_trip": [inverse_point.x, inverse_point.y],
    }

    bezier_cases: list[JsonValue] = [
        {
            "p": [0.0, 0.1, 0.9, 1.0],
            "t": t,
            "expected": cubic_scalar(0.0, 0.1, 0.9, 1.0, t),
        }
        for t in (0.0, 0.3, 0.5, 0.75, 1.0)
    ]

    two_bone = build_two_bone_rig()
    two_bone_endpoints = compute_bone_endpoints(two_bone)
    biped = build_biped_rig("rig_biped_alpha")
    biped_endpoints = compute_bone_endpoints(biped)
    tracked_bones = ("root", "hips", "head", "hand_l", "hand_r", "toe_l", "toe_r")
    endpoint_cases: JsonValue = {
        "rig-two-bone.json": {
            bone_id: {
                "origin": [origin.x, origin.y],
                "tip": [tip.x, tip.y],
            }
            for bone_id, (origin, tip) in sorted(two_bone_endpoints.items())
        },
        "rig-canonical-biped.json": {
            bone_id: {
                "origin": [biped_endpoints[bone_id][0].x, biped_endpoints[bone_id][0].y],
                "tip": [biped_endpoints[bone_id][1].x, biped_endpoints[bone_id][1].y],
            }
            for bone_id in tracked_bones
        },
    }

    return {
        "description": (
            "Golden vectors shared by the Python and TypeScript math kernels. "
            "Regenerate with backend/scripts/generate_fixtures.py."
        ),
        "rng": {"cases": rng_cases, "string_seeds": string_seeds},
        "angles": angle_cases,
        "affine": affine_case,
        "bezier": bezier_cases,
        "bone_endpoints": endpoint_cases,
    }


def write_json(path: Path, value: JsonValue) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json_pretty(value), encoding="utf-8")
    print(f"wrote {path.relative_to(REPO_ROOT)}")


def main() -> None:
    biped_project = build_biped_project()
    issues = validate_project_document(biped_project)
    if issues:
        raise DomainValidationError(tuple(issues))

    fixtures = SAMPLES / "fixtures"
    write_json(fixtures / "rig-two-bone.json", build_two_bone_rig().model_dump(mode="json"))
    write_json(
        fixtures / "rig-canonical-biped.json",
        build_biped_rig("rig_biped_alpha").model_dump(mode="json"),
    )
    write_json(fixtures / "scene-empty.json", build_scene_empty().model_dump(mode="json"))
    write_json(
        fixtures / "scene-one-character.json",
        build_scene_one_character().model_dump(mode="json"),
    )
    write_json(
        fixtures / "scene-two-characters.json",
        build_scene_two_characters().model_dump(mode="json"),
    )
    write_json(fixtures / "math-golden.json", build_math_goldens())

    projects = SAMPLES / "projects"
    write_json(
        projects / "empty-project.rigstory.json", build_empty_project().model_dump(mode="json")
    )
    write_json(projects / "biped-demo.rigstory.json", biped_project.model_dump(mode="json"))

    generated_project = build_generated_project()
    generated_issues = validate_project_document(generated_project)
    if generated_issues:
        raise DomainValidationError(tuple(generated_issues))
    write_json(
        projects / "generated-character.rigstory.json",
        generated_project.model_dump(mode="json"),
    )

    for name, payload in build_invalid_fixtures().items():
        write_json(SAMPLES / "invalid" / name, payload)


if __name__ == "__main__":
    main()
