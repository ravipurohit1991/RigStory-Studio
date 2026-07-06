from __future__ import annotations

import re
from dataclasses import asdict
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api.deps import get_project_store
from app.domain.errors import DomainValidationError
from app.domain.ids import new_project_id
from app.schemas.projects import (
    MigrationReport,
    ProjectCreate,
    ProjectImportRead,
    ProjectRead,
    ProjectRevisionSummary,
    ProjectSummary,
    ProjectUpdate,
)
from app.services.project_archive import (
    ArchiveConflictError,
    ArchiveError,
    build_project_archive,
    load_archive_for_import,
    write_imported_assets,
)
from app.services.project_store import (
    FileProjectStore,
    ProjectConflictError,
    ProjectNotFoundError,
    ProjectValidationStoreError,
)

router = APIRouter(prefix="/projects", tags=["projects"])
ProjectStoreDep = Annotated[FileProjectStore, Depends(get_project_store)]
MAX_PROJECT_ARCHIVE_BYTES = 50 * 1024 * 1024


@router.get("", response_model=list[ProjectSummary])
def list_projects(store: ProjectStoreDep) -> list[ProjectSummary]:
    return [
        ProjectSummary(id=project.id, name=project.name, revision=project.revision)
        for project in store.list_projects()
    ]


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    store: ProjectStoreDep,
) -> ProjectRead:
    try:
        stored = store.create_project(name=payload.name, document=payload.document)
    except ProjectConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="project already exists",
        ) from exc
    except DomainValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[asdict(issue) for issue in exc.issues],
        ) from exc
    return ProjectRead(document=stored.document, revision=stored.revision)


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(
    project_id: str,
    store: ProjectStoreDep,
) -> ProjectRead:
    try:
        stored = store.get_project(project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="project not found",
        ) from exc
    return ProjectRead(document=stored.document, revision=stored.revision)


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: str,
    payload: ProjectUpdate,
    store: ProjectStoreDep,
) -> ProjectRead:
    try:
        stored = store.save_project(
            project_id,
            payload.document,
            expected_revision=payload.expected_revision,
        )
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="project not found",
        ) from exc
    except ProjectConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="stale project revision",
        ) from exc
    except ProjectValidationStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except DomainValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[asdict(issue) for issue in exc.issues],
        ) from exc
    return ProjectRead(document=stored.document, revision=stored.revision)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_project(
    project_id: str,
    store: ProjectStoreDep,
) -> Response:
    try:
        store.delete_project(project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="project not found",
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{project_id}/duplicate",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
)
def duplicate_project(
    project_id: str,
    store: ProjectStoreDep,
) -> ProjectRead:
    try:
        stored = store.duplicate_project(project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="project not found",
        ) from exc
    return ProjectRead(document=stored.document, revision=stored.revision)


def _archive_filename(name: str, project_id: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", name).strip("-").lower()
    return f"{slug or project_id}.rigstory.zip"


@router.get(
    "/{project_id}/export",
    response_class=Response,
    responses={200: {"content": {"application/zip": {}}}},
)
def export_project_archive(
    project_id: str,
    store: ProjectStoreDep,
) -> Response:
    """Download the project as a portable, checksummed archive."""
    try:
        stored = store.get_project(project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="project not found",
        ) from exc
    try:
        payload = build_project_archive(
            stored.document.model_dump(mode="json"),
            assets_root=store.base_path,
        )
    except ArchiveError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    filename = _archive_filename(stored.document.project.name, project_id)
    return Response(
        content=payload,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/import",
    response_model=ProjectImportRead,
    status_code=status.HTTP_201_CREATED,
)
async def import_project_archive(
    request: Request,
    store: ProjectStoreDep,
    on_conflict: Literal["new_id", "fail"] = "new_id",
) -> ProjectImportRead:
    """Import a portable archive uploaded as a raw ``application/zip`` body."""
    data = await request.body()
    if not data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="request body must contain an archive",
        )
    if len(data) > MAX_PROJECT_ARCHIVE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"archive exceeds {MAX_PROJECT_ARCHIVE_BYTES} byte limit",
        )
    try:
        imported = load_archive_for_import(
            data,
            existing_project_ids=store.project_ids(),
            on_conflict=on_conflict,
            new_project_id=new_project_id(),
        )
    except ArchiveConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except ArchiveError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except DomainValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[asdict(issue) for issue in exc.issues],
        ) from exc

    imported_assets = write_imported_assets(store.base_path, imported.assets)
    try:
        stored = store.create_project(
            name=imported.loaded.document.project.name,
            document=imported.loaded.document,
        )
    except ProjectConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="project already exists",
        ) from exc
    except DomainValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[asdict(issue) for issue in exc.issues],
        ) from exc

    return ProjectImportRead(
        document=stored.document,
        revision=stored.revision,
        original_project_id=imported.original_project_id,
        id_reassigned=imported.id_reassigned,
        migration=MigrationReport(
            from_version=imported.migration.from_version,
            to_version=imported.migration.to_version,
            applied=list(imported.migration.applied),
        ),
        imported_assets=imported_assets,
        warnings=list(imported.warnings),
    )


@router.get("/{project_id}/revisions", response_model=list[ProjectRevisionSummary])
def list_project_revisions(
    project_id: str,
    store: ProjectStoreDep,
) -> list[ProjectRevisionSummary]:
    try:
        revisions = store.list_revisions(project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="project not found",
        ) from exc
    return [
        ProjectRevisionSummary(id=revision.id, sequence=revision.sequence) for revision in revisions
    ]


@router.post("/{project_id}/restore/{revision_id}", response_model=ProjectRead)
def restore_project_revision(
    project_id: str,
    revision_id: str,
    store: ProjectStoreDep,
) -> ProjectRead:
    try:
        stored = store.restore_revision(project_id, revision_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="revision not found",
        ) from exc
    return ProjectRead(document=stored.document, revision=stored.revision)
