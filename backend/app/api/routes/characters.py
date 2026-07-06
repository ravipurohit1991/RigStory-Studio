from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import (
    get_app_settings,
    get_character_generation_service,
    get_job_runner,
    get_project_store,
)
from app.application.characters.generate import (
    CharacterGenerationInput,
    CharacterGenerationResult,
    CharacterGenerationService,
)
from app.application.jobs import Job, JobContext, JobRunner
from app.core.config import Settings
from app.domain.character import CharacterDefinition
from app.domain.character_builder import (
    PRESET_REQUESTS,
    CharacterBuilderRequest,
    build_procedural_character,
)
from app.domain.errors import DomainValidationError
from app.infrastructure.llm.provider import GenerationOptions
from app.schemas.characters import (
    CharacterBuilderPresetRead,
    CharacterBuildRead,
    CharacterGenerationRequest,
    CharacterMutationResult,
    CharacterRead,
    CharacterWrite,
)
from app.services.project_store import FileProjectStore, ProjectConflictError, ProjectNotFoundError

router = APIRouter(tags=["characters"])
ProjectStoreDep = Annotated[FileProjectStore, Depends(get_project_store)]
JobRunnerDep = Annotated[JobRunner, Depends(get_job_runner)]
GenerationServiceDep = Annotated[
    CharacterGenerationService, Depends(get_character_generation_service)
]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]


def validation_exception(exc: DomainValidationError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=[asdict(issue) for issue in exc.issues],
    )


@router.get(
    "/characters/builder-presets",
    response_model=list[CharacterBuilderPresetRead],
)
def list_character_builder_presets() -> list[CharacterBuilderPresetRead]:
    return [CharacterBuilderPresetRead(request=request) for request in PRESET_REQUESTS]


@router.post(
    "/characters/build",
    response_model=CharacterBuildRead,
)
def build_character(payload: CharacterBuilderRequest) -> CharacterBuildRead:
    return CharacterBuildRead.model_validate(
        build_procedural_character(payload).model_dump(mode="json")
    )


@router.post(
    "/projects/{project_id}/characters/generate",
    response_model=Job,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_project_character(
    project_id: str,
    payload: CharacterGenerationRequest,
    runner: JobRunnerDep,
    service: GenerationServiceDep,
    settings: SettingsDep,
) -> Job:
    """Start an AI character-generation job (specs §23.2, returns 202 + a job)."""
    options = GenerationOptions(
        temperature=payload.temperature
        if payload.temperature is not None
        else settings.ollama_temperature,
        keep_alive=settings.ollama_keep_alive,
        timeout_seconds=payload.timeout_seconds
        if payload.timeout_seconds is not None
        else settings.ollama_generation_timeout_seconds,
        num_ctx=settings.ollama_num_ctx,
    )
    generation_input = CharacterGenerationInput(
        project_id=project_id,
        expected_revision=payload.expected_revision,
        model=payload.model,
        description=payload.description,
        form=payload.form,
        options=options,
    )

    async def body(ctx: JobContext) -> CharacterGenerationResult:
        return await service.generate(generation_input, ctx)

    return await runner.submit(kind="character_generation", body=body)


@router.get(
    "/projects/{project_id}/characters",
    response_model=list[CharacterDefinition],
)
def list_project_characters(
    project_id: str,
    store: ProjectStoreDep,
) -> tuple[CharacterDefinition, ...]:
    try:
        return store.list_characters(project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="project not found",
        ) from exc


@router.post(
    "/projects/{project_id}/characters",
    response_model=CharacterMutationResult,
    status_code=status.HTTP_201_CREATED,
)
def create_project_character(
    project_id: str,
    payload: CharacterWrite,
    store: ProjectStoreDep,
) -> CharacterMutationResult:
    try:
        stored = store.create_character(
            project_id,
            payload.character,
            payload.expected_revision,
        )
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="project not found",
        ) from exc
    except ProjectConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="character exists",
        ) from exc
    except DomainValidationError as exc:
        raise validation_exception(exc) from exc
    return CharacterMutationResult(document=stored.document, revision=stored.revision)


@router.get("/characters/{character_id}", response_model=CharacterRead)
def get_character(
    character_id: str,
    store: ProjectStoreDep,
) -> CharacterRead:
    try:
        stored = store.get_character(character_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="character not found",
        ) from exc
    return CharacterRead(
        project_id=stored.project_id,
        character=stored.character,
        revision=stored.revision,
    )


@router.patch("/characters/{character_id}", response_model=CharacterMutationResult)
def update_character(
    character_id: str,
    payload: CharacterWrite,
    store: ProjectStoreDep,
) -> CharacterMutationResult:
    if payload.character.id != character_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="character id does not match route",
        )
    try:
        stored = store.get_character(character_id)
        updated = store.save_character(
            stored.project_id,
            payload.character,
            payload.expected_revision,
        )
    except ProjectConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="stale project revision",
        ) from exc
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="character not found",
        ) from exc
    except DomainValidationError as exc:
        raise validation_exception(exc) from exc
    return CharacterMutationResult(document=updated.document, revision=updated.revision)


@router.delete(
    "/characters/{character_id}",
    response_model=CharacterMutationResult,
)
def delete_character(
    character_id: str,
    expected_revision: str,
    store: ProjectStoreDep,
) -> CharacterMutationResult:
    try:
        stored = store.get_character(character_id)
        updated = store.delete_character(
            stored.project_id,
            character_id,
            expected_revision,
        )
    except ProjectConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="stale project revision",
        ) from exc
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="character not found",
        ) from exc
    except DomainValidationError as exc:
        raise validation_exception(exc) from exc
    return CharacterMutationResult(document=updated.document, revision=updated.revision)
