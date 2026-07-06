from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_project_store
from app.domain.errors import DomainValidationError
from app.domain.scene import SceneDefinition, validate_scene
from app.domain.scene_snapshot import build_scene_snapshot
from app.schemas.scenes import (
    SceneMutationResult,
    SceneRead,
    SceneSnapshotRead,
    SceneValidationRead,
    SceneWrite,
)
from app.services.project_store import FileProjectStore, ProjectConflictError, ProjectNotFoundError

router = APIRouter(tags=["scenes"])
ProjectStoreDep = Annotated[FileProjectStore, Depends(get_project_store)]


def validation_exception(exc: DomainValidationError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=[asdict(issue) for issue in exc.issues],
    )


@router.get("/projects/{project_id}/scenes", response_model=list[SceneDefinition])
def list_project_scenes(project_id: str, store: ProjectStoreDep) -> tuple[SceneDefinition, ...]:
    try:
        return store.list_scenes(project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="project not found") from exc


@router.post(
    "/projects/{project_id}/scenes",
    response_model=SceneMutationResult,
    status_code=status.HTTP_201_CREATED,
)
def create_project_scene(
    project_id: str,
    payload: SceneWrite,
    store: ProjectStoreDep,
) -> SceneMutationResult:
    try:
        stored = store.create_scene(project_id, payload.scene, payload.expected_revision)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="project not found") from exc
    except ProjectConflictError as exc:
        raise HTTPException(status_code=409, detail="scene exists or revision is stale") from exc
    except DomainValidationError as exc:
        raise validation_exception(exc) from exc
    return SceneMutationResult(document=stored.document, revision=stored.revision)


@router.get("/scenes/{scene_id}", response_model=SceneRead)
def get_scene(scene_id: str, store: ProjectStoreDep) -> SceneRead:
    try:
        stored = store.get_scene(scene_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="scene not found") from exc
    return SceneRead(project_id=stored.project_id, scene=stored.scene, revision=stored.revision)


@router.patch("/scenes/{scene_id}", response_model=SceneMutationResult)
def update_scene(
    scene_id: str,
    payload: SceneWrite,
    store: ProjectStoreDep,
) -> SceneMutationResult:
    if payload.scene.id != scene_id:
        raise HTTPException(status_code=422, detail="scene id does not match route")
    try:
        stored = store.get_scene(scene_id)
        updated = store.save_scene(stored.project_id, payload.scene, payload.expected_revision)
    except ProjectConflictError as exc:
        raise HTTPException(status_code=409, detail="stale project revision") from exc
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="scene not found") from exc
    except DomainValidationError as exc:
        raise validation_exception(exc) from exc
    return SceneMutationResult(document=updated.document, revision=updated.revision)


@router.delete(
    "/scenes/{scene_id}",
    response_model=SceneMutationResult,
)
def delete_scene(
    scene_id: str,
    expected_revision: str,
    store: ProjectStoreDep,
) -> SceneMutationResult:
    try:
        stored = store.get_scene(scene_id)
        updated = store.delete_scene(stored.project_id, scene_id, expected_revision)
    except ProjectConflictError as exc:
        raise HTTPException(status_code=409, detail="stale project revision") from exc
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="scene not found") from exc
    except DomainValidationError as exc:
        raise validation_exception(exc) from exc
    return SceneMutationResult(document=updated.document, revision=updated.revision)


@router.post(
    "/scenes/{scene_id}/validate",
    response_model=SceneValidationRead,
)
def validate_scene_route(scene_id: str, store: ProjectStoreDep) -> SceneValidationRead:
    try:
        stored = store.get_scene(scene_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="scene not found") from exc
    return SceneValidationRead(issues=tuple(validate_scene(stored.scene)))


@router.get("/scenes/{scene_id}/snapshot", response_model=SceneSnapshotRead)
def get_scene_snapshot(scene_id: str, store: ProjectStoreDep) -> SceneSnapshotRead:
    try:
        stored_scene = store.get_scene(scene_id)
        project = store.get_project(stored_scene.project_id).document
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="scene not found") from exc
    characters = {character.id: character for character in project.characters}
    snapshot = build_scene_snapshot(stored_scene.scene, characters=characters)
    canonical = snapshot.canonical_json()
    return SceneSnapshotRead(
        snapshot=snapshot,
        canonical_json=canonical,
        byte_length=len(canonical.encode("utf-8")),
    )
