from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.domain.errors import ValidationIssue
from app.domain.scene import SceneDefinition
from app.domain.scene_snapshot import SceneSnapshot
from app.schemas.projects import ProjectRead


class SceneRead(BaseModel):
    project_id: str
    scene: SceneDefinition
    revision: str

    model_config = ConfigDict(frozen=True)


class SceneWrite(BaseModel):
    scene: SceneDefinition
    expected_revision: str

    model_config = ConfigDict(frozen=True)


class SceneMutationResult(ProjectRead):
    pass


class SceneValidationRead(BaseModel):
    issues: tuple[ValidationIssue, ...]

    model_config = ConfigDict(frozen=True)


class SceneSnapshotRead(BaseModel):
    snapshot: SceneSnapshot
    canonical_json: str
    byte_length: int

    model_config = ConfigDict(frozen=True)
