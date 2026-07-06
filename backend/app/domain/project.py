"""Versioned project document: the native persisted format.

``parse_project_document`` validates shape only. ``validate_project_document``
checks cross-object invariants and reference integrity across characters,
scenes, and clips. ``load_project_document`` combines migration, parsing, and
invariant validation for untrusted input.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import Field

from app.domain.canonical import JsonValue
from app.domain.character import CharacterDefinition, validate_character
from app.domain.clip import (
    AnimationClip,
    BoneRotationTrack,
    BoneScaleTrack,
    validate_clip,
)
from app.domain.common import DomainModel
from app.domain.errors import DomainValidationError, ValidationIssue
from app.domain.generation import GenerationRecord
from app.domain.ids import ProjectId, SchemaVersionStr
from app.domain.migrations import MigrationResult, migrate_project_document
from app.domain.motion_plan import MotionPlan
from app.domain.scene import SceneDefinition, validate_scene
from app.domain.versioning import PROJECT_FORMAT, PROJECT_SCHEMA_VERSION

SHA256_PATTERN = r"^[0-9a-f]{64}$"


class ProjectInfo(DomainModel):
    id: ProjectId
    name: str = Field(min_length=1)


class AssetManifestEntry(DomainModel):
    id: str = Field(pattern=r"^asset_[a-z0-9][a-z0-9_-]*$")
    sha256: str = Field(pattern=SHA256_PATTERN)
    media_type: str = Field(min_length=1)
    display_name: str = ""


class ProjectDocument(DomainModel):
    format: str = Field(pattern=rf"^{PROJECT_FORMAT}$")
    schema_version: SchemaVersionStr
    engine_version: SchemaVersionStr
    project: ProjectInfo
    characters: tuple[CharacterDefinition, ...] = ()
    scenes: tuple[SceneDefinition, ...] = ()
    clips: tuple[AnimationClip, ...] = ()
    motion_plans: tuple[MotionPlan, ...] = ()
    generation_records: tuple[GenerationRecord, ...] = ()
    asset_manifest: tuple[AssetManifestEntry, ...] = ()


def parse_project_document(raw: dict[str, JsonValue]) -> ProjectDocument:
    return ProjectDocument.model_validate(raw)


def validate_project_document(document: ProjectDocument) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    if document.schema_version != str(PROJECT_SCHEMA_VERSION):
        issues.append(
            ValidationIssue(
                "PROJECT_UNSUPPORTED_VERSION",
                f"schema_version {document.schema_version!r} is not the current "
                f"{PROJECT_SCHEMA_VERSION}; migrate the document first",
                "schema_version",
            )
        )

    character_ids: set[str] = set()
    for index, character in enumerate(document.characters):
        if character.id in character_ids:
            issues.append(
                ValidationIssue(
                    "PROJECT_DUPLICATE_ID",
                    f"character id {character.id!r} is defined more than once",
                    f"characters[{index}].id",
                )
            )
        character_ids.add(character.id)
        issues.extend(validate_character(character, f"characters[{index}]"))

    scene_ids: set[str] = set()
    actors_by_scene: dict[str, dict[str, str]] = {}
    for index, scene in enumerate(document.scenes):
        if scene.id in scene_ids:
            issues.append(
                ValidationIssue(
                    "PROJECT_DUPLICATE_ID",
                    f"scene id {scene.id!r} is defined more than once",
                    f"scenes[{index}].id",
                )
            )
        scene_ids.add(scene.id)
        issues.extend(validate_scene(scene, f"scenes[{index}]"))
        actors_by_scene[scene.id] = {actor.id: actor.character_id for actor in scene.actors}
        for actor_index, actor in enumerate(scene.actors):
            if actor.character_id not in character_ids:
                issues.append(
                    ValidationIssue(
                        "SCENE_UNKNOWN_CHARACTER",
                        f"actor {actor.id!r} references unknown character {actor.character_id!r}",
                        f"scenes[{index}].actors[{actor_index}].character_id",
                    )
                )

    characters_by_id = {character.id: character for character in document.characters}
    clip_ids: set[str] = set()
    for index, clip in enumerate(document.clips):
        clip_path = f"clips[{index}]"
        if clip.id in clip_ids:
            issues.append(
                ValidationIssue(
                    "PROJECT_DUPLICATE_ID",
                    f"clip id {clip.id!r} is defined more than once",
                    f"{clip_path}.id",
                )
            )
        clip_ids.add(clip.id)
        issues.extend(validate_clip(clip, clip_path))

        scene_actors = actors_by_scene.get(clip.scene_id)
        if scene_actors is None:
            issues.append(
                ValidationIssue(
                    "CLIP_UNKNOWN_SCENE",
                    f"clip {clip.id!r} references unknown scene {clip.scene_id!r}",
                    f"{clip_path}.scene_id",
                )
            )
            continue
        for track_index, track in enumerate(clip.tracks):
            track_path = f"{clip_path}.tracks[{track_index}]"
            character_id = scene_actors.get(track.actor_id)
            if character_id is None:
                issues.append(
                    ValidationIssue(
                        "CLIP_UNKNOWN_ACTOR",
                        f"track {track.id!r} references actor {track.actor_id!r} "
                        f"not present in scene {clip.scene_id!r}",
                        f"{track_path}.actor_id",
                    )
                )
                continue
            bone_id = (
                track.bone_id if isinstance(track, BoneRotationTrack | BoneScaleTrack) else None
            )
            track_character = characters_by_id.get(character_id)
            if bone_id is not None and track_character is not None:
                rig_bone_ids = {bone.id for bone in track_character.rig.bones}
                if bone_id not in rig_bone_ids:
                    issues.append(
                        ValidationIssue(
                            "CLIP_UNKNOWN_BONE",
                            f"track {track.id!r} references bone {bone_id!r} missing "
                            f"from character {character_id!r}",
                            f"{track_path}.bone_id",
                        )
                    )

    plan_ids: set[str] = set()
    for index, plan in enumerate(document.motion_plans):
        plan_path = f"motion_plans[{index}]"
        if plan.id in plan_ids:
            issues.append(
                ValidationIssue(
                    "PROJECT_DUPLICATE_ID",
                    f"motion plan id {plan.id!r} is defined more than once",
                    f"{plan_path}.id",
                )
            )
        plan_ids.add(plan.id)
        scene_actors = actors_by_scene.get(plan.scene_id)
        if scene_actors is None:
            issues.append(
                ValidationIssue(
                    "PLAN_UNKNOWN_SCENE",
                    f"motion plan {plan.id!r} references unknown scene {plan.scene_id!r}",
                    f"{plan_path}.scene_id",
                )
            )
            continue
        for action_index, action in enumerate(plan.actions):
            if action.actor_id not in scene_actors:
                issues.append(
                    ValidationIssue(
                        "PLAN_UNKNOWN_ACTOR",
                        f"plan {plan.id!r} action {action.id!r} references actor "
                        f"{action.actor_id!r} not present in scene {plan.scene_id!r}",
                        f"{plan_path}.actions[{action_index}].actor_id",
                    )
                )

    for index, clip in enumerate(document.clips):
        if clip.source_plan_id is not None and clip.source_plan_id not in plan_ids:
            issues.append(
                ValidationIssue(
                    "CLIP_UNKNOWN_PLAN",
                    f"clip {clip.id!r} references unknown motion plan {clip.source_plan_id!r}",
                    f"clips[{index}].source_plan_id",
                )
            )

    record_ids: set[str] = set()
    for index, record in enumerate(document.generation_records):
        record_path = f"generation_records[{index}]"
        if record.id in record_ids:
            issues.append(
                ValidationIssue(
                    "PROJECT_DUPLICATE_ID",
                    f"generation record id {record.id!r} is defined more than once",
                    f"{record_path}.id",
                )
            )
        record_ids.add(record.id)
        if record.character_id is not None and record.character_id not in character_ids:
            issues.append(
                ValidationIssue(
                    "GENERATION_UNKNOWN_CHARACTER",
                    f"generation record {record.id!r} references unknown character "
                    f"{record.character_id!r}",
                    f"{record_path}.character_id",
                )
            )
        if record.plan_id is not None and record.plan_id not in plan_ids:
            issues.append(
                ValidationIssue(
                    "GENERATION_UNKNOWN_PLAN",
                    f"generation record {record.id!r} references unknown motion plan "
                    f"{record.plan_id!r}",
                    f"{record_path}.plan_id",
                )
            )
    return issues


@dataclass(frozen=True, slots=True)
class LoadedProject:
    document: ProjectDocument
    migration: MigrationResult


def load_project_document(raw: dict[str, JsonValue]) -> LoadedProject:
    """Migrate, parse, and invariant-check an untrusted raw project document."""
    migration = migrate_project_document(raw)
    document = parse_project_document(migration.document)
    issues = validate_project_document(document)
    if issues:
        raise DomainValidationError(tuple(issues))
    return LoadedProject(document=document, migration=migration)
