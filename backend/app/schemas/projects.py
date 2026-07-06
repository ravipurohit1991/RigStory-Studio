from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.domain.project import ProjectDocument


class ProjectSummary(BaseModel):
    id: str
    name: str
    revision: str

    model_config = ConfigDict(frozen=True)


class ProjectRead(BaseModel):
    document: ProjectDocument
    revision: str

    model_config = ConfigDict(frozen=True)


class ProjectCreate(BaseModel):
    name: str = Field(default="Untitled Project", min_length=1)
    document: ProjectDocument | None = None

    model_config = ConfigDict(frozen=True)


class ProjectUpdate(BaseModel):
    document: ProjectDocument
    expected_revision: str

    model_config = ConfigDict(frozen=True)


class ProjectRevisionSummary(BaseModel):
    id: str
    sequence: int

    model_config = ConfigDict(frozen=True)


class MigrationReport(BaseModel):
    from_version: str
    to_version: str
    applied: list[str] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)


class ProjectImportRead(BaseModel):
    document: ProjectDocument
    revision: str
    original_project_id: str
    id_reassigned: bool
    migration: MigrationReport
    imported_assets: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)
