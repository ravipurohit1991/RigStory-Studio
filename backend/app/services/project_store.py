from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.domain.canonical import JsonValue, canonical_json_pretty
from app.domain.character import CharacterDefinition
from app.domain.clip import AnimationClip
from app.domain.generation import GenerationRecord
from app.domain.ids import new_project_id, new_revision_id
from app.domain.motion_plan import MotionPlan
from app.domain.project import ProjectDocument, ProjectInfo, load_project_document
from app.domain.scene import SceneDefinition
from app.domain.versioning import ENGINE_VERSION, PROJECT_FORMAT, PROJECT_SCHEMA_VERSION


class ProjectStoreError(Exception):
    """Base class for project persistence errors."""


class ProjectNotFoundError(ProjectStoreError):
    pass


class ProjectConflictError(ProjectStoreError):
    pass


class ProjectValidationStoreError(ProjectStoreError):
    pass


class ProjectMetadata(BaseModel):
    project_id: str
    current_revision: str
    revision_sequence: int = Field(ge=1)
    last_good_revision: str

    model_config = ConfigDict(frozen=True)


@dataclass(frozen=True, slots=True)
class StoredProject:
    document: ProjectDocument
    revision: str


@dataclass(frozen=True, slots=True)
class StoredProjectSummary:
    id: str
    name: str
    revision: str


@dataclass(frozen=True, slots=True)
class StoredProjectRevision:
    id: str
    sequence: int


@dataclass(frozen=True, slots=True)
class StoredCharacter:
    project_id: str
    character: CharacterDefinition
    revision: str


@dataclass(frozen=True, slots=True)
class StoredScene:
    project_id: str
    scene: SceneDefinition
    revision: str


@dataclass(frozen=True, slots=True)
class StoredMotionPlan:
    project_id: str
    plan: MotionPlan
    revision: str


@dataclass(frozen=True, slots=True)
class StoredClip:
    project_id: str
    document: ProjectDocument
    clip: AnimationClip
    revision: str


def _project_dir(root: Path, project_id: str) -> Path:
    return root / project_id


def _current_path(root: Path, project_id: str) -> Path:
    return _project_dir(root, project_id) / "current.json"


def _metadata_path(root: Path, project_id: str) -> Path:
    return _project_dir(root, project_id) / "metadata.json"


def _revisions_dir(root: Path, project_id: str) -> Path:
    return _project_dir(root, project_id) / "revisions"


def _backups_dir(root: Path, project_id: str) -> Path:
    return _project_dir(root, project_id) / "backups"


def _revision_path(root: Path, project_id: str, sequence: int, revision: str) -> Path:
    return _revisions_dir(root, project_id) / f"{sequence:06d}-{revision}.json"


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    temp_path.write_text(text, encoding="utf-8")
    os.replace(temp_path, path)


def _metadata_json(metadata: ProjectMetadata) -> str:
    return canonical_json_pretty(metadata.model_dump(mode="json"))


def create_empty_project_document(name: str) -> ProjectDocument:
    return ProjectDocument(
        format=PROJECT_FORMAT,
        schema_version=str(PROJECT_SCHEMA_VERSION),
        engine_version=str(ENGINE_VERSION),
        project=ProjectInfo(id=new_project_id(), name=name),
    )


class FileProjectStore:
    """Revisioned local project document store.

    The store persists native project JSON on disk and validates the full
    document before writing and updates ``current.json`` only after the matching
    revision file has been written, so a failed save leaves the last good
    revision available.
    """

    def __init__(self, asset_store_path: Path) -> None:
        self.base_path = asset_store_path
        self.root = asset_store_path / "projects"

    def project_ids(self) -> frozenset[str]:
        """Ids of every stored project (directory names equal project ids)."""
        if not self.root.exists():
            return frozenset()
        return frozenset(entry.name for entry in self.root.iterdir() if entry.is_dir())

    def list_projects(self) -> list[StoredProjectSummary]:
        if not self.root.exists():
            return []
        summaries: list[StoredProjectSummary] = []
        for entry in sorted(self.root.iterdir(), key=lambda path: path.name):
            if not entry.is_dir():
                continue
            try:
                metadata = self._read_metadata(entry.name)
                document = self.get_project(entry.name).document
            except (FileNotFoundError, ProjectNotFoundError, ValidationError, json.JSONDecodeError):
                continue
            summaries.append(
                StoredProjectSummary(
                    id=document.project.id,
                    name=document.project.name,
                    revision=metadata.current_revision,
                )
            )
        return summaries

    def create_project(
        self,
        *,
        name: str,
        document: ProjectDocument | None = None,
    ) -> StoredProject:
        active_document = document or create_empty_project_document(name)
        return self._write_new_project(active_document)

    def get_project(self, project_id: str) -> StoredProject:
        current_path = _current_path(self.root, project_id)
        if not current_path.exists():
            raise ProjectNotFoundError(project_id)
        original_text = current_path.read_text(encoding="utf-8")
        raw = json.loads(original_text)
        loaded = load_project_document(raw)
        metadata = self._read_metadata(project_id)
        if loaded.migration.applied:
            # In-place schema upgrade: keep the pre-migration bytes as a backup,
            # then persist the migrated document as a normal new revision so the
            # upgrade is recoverable and visible in project history.
            backup_path = _backups_dir(self.root, project_id) / (
                f"pre-upgrade-{loaded.migration.from_version}-{metadata.current_revision}.json"
            )
            if not backup_path.exists():
                _atomic_write_text(backup_path, original_text)
            return self._append_revision(loaded.document, metadata)
        return StoredProject(document=loaded.document, revision=metadata.current_revision)

    def save_project(
        self,
        project_id: str,
        document: ProjectDocument,
        expected_revision: str,
    ) -> StoredProject:
        metadata = self._read_metadata(project_id)
        if metadata.current_revision != expected_revision:
            raise ProjectConflictError(project_id)
        if document.project.id != project_id:
            raise ProjectValidationStoreError("document project id does not match route project id")
        return self._append_revision(document, metadata)

    def duplicate_project(self, project_id: str) -> StoredProject:
        source = self.get_project(project_id).document
        duplicate_id = new_project_id()
        duplicate = source.model_copy(
            update={
                "project": source.project.model_copy(
                    update={"id": duplicate_id, "name": f"{source.project.name} Copy"}
                )
            }
        )
        return self._write_new_project(duplicate)

    def list_characters(self, project_id: str) -> tuple[CharacterDefinition, ...]:
        return self.get_project(project_id).document.characters

    def get_character(self, character_id: str) -> StoredCharacter:
        if not self.root.exists():
            raise ProjectNotFoundError(character_id)
        for summary in self.list_projects():
            stored = self.get_project(summary.id)
            for character in stored.document.characters:
                if character.id == character_id:
                    return StoredCharacter(
                        project_id=summary.id,
                        character=character,
                        revision=stored.revision,
                    )
        raise ProjectNotFoundError(character_id)

    def create_character(
        self,
        project_id: str,
        character: CharacterDefinition,
        expected_revision: str,
    ) -> StoredProject:
        stored = self.get_project(project_id)
        if any(existing.id == character.id for existing in stored.document.characters):
            raise ProjectConflictError(character.id)
        document = stored.document.model_copy(
            update={"characters": (*stored.document.characters, character)}
        )
        return self.save_project(project_id, document, expected_revision)

    def commit_generated_character(
        self,
        project_id: str,
        character: CharacterDefinition,
        record: GenerationRecord,
        expected_revision: str,
    ) -> StoredProject:
        """Append a generated character and its generation record in one revision.

        Both land in the same revision so a generated character and its audit
        record are always committed together, or not at all.
        """
        stored = self.get_project(project_id)
        if any(existing.id == character.id for existing in stored.document.characters):
            raise ProjectConflictError(character.id)
        document = stored.document.model_copy(
            update={
                "characters": (*stored.document.characters, character),
                "generation_records": (*stored.document.generation_records, record),
            }
        )
        return self.save_project(project_id, document, expected_revision)

    def save_character(
        self,
        project_id: str,
        character: CharacterDefinition,
        expected_revision: str,
    ) -> StoredProject:
        stored = self.get_project(project_id)
        if not any(existing.id == character.id for existing in stored.document.characters):
            raise ProjectNotFoundError(character.id)
        document = stored.document.model_copy(
            update={
                "characters": tuple(
                    character if existing.id == character.id else existing
                    for existing in stored.document.characters
                )
            }
        )
        return self.save_project(project_id, document, expected_revision)

    def delete_character(
        self,
        project_id: str,
        character_id: str,
        expected_revision: str,
    ) -> StoredProject:
        stored = self.get_project(project_id)
        if not any(character.id == character_id for character in stored.document.characters):
            raise ProjectNotFoundError(character_id)
        document = stored.document.model_copy(
            update={
                "characters": tuple(
                    character
                    for character in stored.document.characters
                    if character.id != character_id
                )
            }
        )
        return self.save_project(project_id, document, expected_revision)

    def list_scenes(self, project_id: str) -> tuple[SceneDefinition, ...]:
        return self.get_project(project_id).document.scenes

    def get_scene(self, scene_id: str) -> StoredScene:
        if not self.root.exists():
            raise ProjectNotFoundError(scene_id)
        for summary in self.list_projects():
            stored = self.get_project(summary.id)
            for scene in stored.document.scenes:
                if scene.id == scene_id:
                    return StoredScene(
                        project_id=summary.id,
                        scene=scene,
                        revision=stored.revision,
                    )
        raise ProjectNotFoundError(scene_id)

    def create_scene(
        self,
        project_id: str,
        scene: SceneDefinition,
        expected_revision: str,
    ) -> StoredProject:
        stored = self.get_project(project_id)
        if any(existing.id == scene.id for existing in stored.document.scenes):
            raise ProjectConflictError(scene.id)
        document = stored.document.model_copy(update={"scenes": (*stored.document.scenes, scene)})
        return self.save_project(project_id, document, expected_revision)

    def save_scene(
        self,
        project_id: str,
        scene: SceneDefinition,
        expected_revision: str,
    ) -> StoredProject:
        stored = self.get_project(project_id)
        if not any(existing.id == scene.id for existing in stored.document.scenes):
            raise ProjectNotFoundError(scene.id)
        document = stored.document.model_copy(
            update={
                "scenes": tuple(
                    scene if existing.id == scene.id else existing
                    for existing in stored.document.scenes
                )
            }
        )
        return self.save_project(project_id, document, expected_revision)

    def delete_scene(
        self,
        project_id: str,
        scene_id: str,
        expected_revision: str,
    ) -> StoredProject:
        stored = self.get_project(project_id)
        if not any(scene.id == scene_id for scene in stored.document.scenes):
            raise ProjectNotFoundError(scene_id)
        document = stored.document.model_copy(
            update={
                "scenes": tuple(scene for scene in stored.document.scenes if scene.id != scene_id)
            }
        )
        return self.save_project(project_id, document, expected_revision)

    def get_motion_plan(self, plan_id: str) -> StoredMotionPlan:
        if not self.root.exists():
            raise ProjectNotFoundError(plan_id)
        for summary in self.list_projects():
            stored = self.get_project(summary.id)
            for plan in stored.document.motion_plans:
                if plan.id == plan_id:
                    return StoredMotionPlan(
                        project_id=summary.id,
                        plan=plan,
                        revision=stored.revision,
                    )
        raise ProjectNotFoundError(plan_id)

    def get_clip(self, clip_id: str) -> StoredClip:
        if not self.root.exists():
            raise ProjectNotFoundError(clip_id)
        for summary in self.list_projects():
            stored = self.get_project(summary.id)
            for clip in stored.document.clips:
                if clip.id == clip_id:
                    return StoredClip(
                        project_id=summary.id,
                        document=stored.document,
                        clip=clip,
                        revision=stored.revision,
                    )
        raise ProjectNotFoundError(clip_id)

    def commit_motion_plan(
        self,
        project_id: str,
        plan: MotionPlan,
        record: GenerationRecord,
        expected_revision: str,
    ) -> StoredProject:
        """Append a generated motion plan and its audit record in one revision."""
        stored = self.get_project(project_id)
        if any(existing.id == plan.id for existing in stored.document.motion_plans):
            raise ProjectConflictError(plan.id)
        document = stored.document.model_copy(
            update={
                "motion_plans": (*stored.document.motion_plans, plan),
                "generation_records": (*stored.document.generation_records, record),
            }
        )
        return self.save_project(project_id, document, expected_revision)

    def save_motion_plan(
        self,
        project_id: str,
        plan: MotionPlan,
        expected_revision: str,
    ) -> StoredProject:
        stored = self.get_project(project_id)
        if not any(existing.id == plan.id for existing in stored.document.motion_plans):
            raise ProjectNotFoundError(plan.id)
        document = stored.document.model_copy(
            update={
                "motion_plans": tuple(
                    plan if existing.id == plan.id else existing
                    for existing in stored.document.motion_plans
                )
            }
        )
        return self.save_project(project_id, document, expected_revision)

    def commit_generation_record(
        self,
        project_id: str,
        record: GenerationRecord,
        expected_revision: str,
    ) -> StoredProject:
        """Append one audit record on its own (used by plan patch generation)."""
        stored = self.get_project(project_id)
        document = stored.document.model_copy(
            update={"generation_records": (*stored.document.generation_records, record)}
        )
        return self.save_project(project_id, document, expected_revision)

    def commit_compiled_clip(
        self,
        project_id: str,
        clip: AnimationClip,
        expected_revision: str,
    ) -> StoredProject:
        """Insert a compiled clip, or replace the existing clip with the same id.

        Recompiles keep the clip id stable so timeline references survive.
        """
        stored = self.get_project(project_id)
        if any(existing.id == clip.id for existing in stored.document.clips):
            clips = tuple(
                clip if existing.id == clip.id else existing for existing in stored.document.clips
            )
        else:
            clips = (*stored.document.clips, clip)
        document = stored.document.model_copy(update={"clips": clips})
        return self.save_project(project_id, document, expected_revision)

    def delete_project(self, project_id: str) -> None:
        project_path = _project_dir(self.root, project_id)
        if not project_path.exists():
            raise ProjectNotFoundError(project_id)
        shutil.rmtree(project_path)

    def list_revisions(self, project_id: str) -> list[StoredProjectRevision]:
        metadata = self._read_metadata(project_id)
        revisions = [
            StoredProjectRevision(id=metadata.current_revision, sequence=metadata.revision_sequence)
        ]
        revisions_by_id: dict[str, StoredProjectRevision] = {
            metadata.current_revision: revisions[0]
        }
        revisions_dir = _revisions_dir(self.root, project_id)
        if revisions_dir.exists():
            for path in revisions_dir.glob("*.json"):
                sequence_text, _, revision_with_suffix = path.name.partition("-")
                revision = revision_with_suffix.removesuffix(".json")
                if not sequence_text.isdigit() or not revision:
                    continue
                revisions_by_id[revision] = StoredProjectRevision(
                    id=revision, sequence=int(sequence_text)
                )
        return sorted(revisions_by_id.values(), key=lambda item: item.sequence)

    def restore_revision(self, project_id: str, revision_id: str) -> StoredProject:
        metadata = self._read_metadata(project_id)
        revision_file = self._find_revision_file(project_id, revision_id)
        if revision_file is None:
            raise ProjectNotFoundError(revision_id)
        raw = json.loads(revision_file.read_text(encoding="utf-8"))
        document = load_project_document(raw).document
        return self._append_revision(document, metadata)

    def _write_new_project(self, document: ProjectDocument) -> StoredProject:
        loaded = load_project_document(document.model_dump(mode="json"))
        project_id = loaded.document.project.id
        project_path = _project_dir(self.root, project_id)
        if project_path.exists():
            raise ProjectConflictError(project_id)
        metadata = ProjectMetadata(
            project_id=project_id,
            current_revision=new_revision_id(),
            revision_sequence=1,
            last_good_revision="",
        )
        metadata = metadata.model_copy(update={"last_good_revision": metadata.current_revision})
        return self._write_revision(loaded.document, metadata)

    def _append_revision(
        self,
        document: ProjectDocument,
        previous: ProjectMetadata,
    ) -> StoredProject:
        loaded = load_project_document(document.model_dump(mode="json"))
        metadata = ProjectMetadata(
            project_id=previous.project_id,
            current_revision=new_revision_id(),
            revision_sequence=previous.revision_sequence + 1,
            last_good_revision=previous.current_revision,
        )
        return self._write_revision(loaded.document, metadata)

    def _write_revision(
        self,
        document: ProjectDocument,
        metadata: ProjectMetadata,
    ) -> StoredProject:
        dumped: JsonValue = document.model_dump(mode="json")
        text = canonical_json_pretty(dumped)
        revision_path = _revision_path(
            self.root,
            document.project.id,
            metadata.revision_sequence,
            metadata.current_revision,
        )
        _atomic_write_text(revision_path, text)
        _atomic_write_text(_current_path(self.root, document.project.id), text)
        _atomic_write_text(_metadata_path(self.root, document.project.id), _metadata_json(metadata))
        return StoredProject(document=document, revision=metadata.current_revision)

    def _read_metadata(self, project_id: str) -> ProjectMetadata:
        metadata_path = _metadata_path(self.root, project_id)
        if not metadata_path.exists():
            raise ProjectNotFoundError(project_id)
        return ProjectMetadata.model_validate_json(metadata_path.read_text(encoding="utf-8"))

    def _find_revision_file(self, project_id: str, revision_id: str) -> Path | None:
        revisions_dir = _revisions_dir(self.root, project_id)
        if not revisions_dir.exists():
            return None
        matches = sorted(revisions_dir.glob(f"*-{revision_id}.json"))
        return matches[-1] if matches else None
