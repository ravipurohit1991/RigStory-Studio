from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import (
    get_app_settings,
    get_job_runner,
    get_motion_plan_compile_service,
    get_motion_plan_service,
    get_project_store,
)
from app.application.jobs import Job, JobContext, JobRunner
from app.application.motion.compile import (
    MotionPlanCompileInput,
    MotionPlanCompileResult,
    MotionPlanCompileService,
)
from app.application.motion.planner import (
    MotionPlanGenerationInput,
    MotionPlanGenerationResult,
    MotionPlanPatchInput,
    MotionPlanPatchResult,
    MotionPlanService,
)
from app.core.config import Settings
from app.domain.errors import DomainValidationError
from app.domain.motion_plan import apply_plan_patch
from app.domain.motion_plan_validation import validate_motion_plan
from app.domain.scene_snapshot import build_scene_snapshot
from app.infrastructure.llm.provider import GenerationOptions
from app.schemas.motion_plans import (
    MotionPlanApplyPatchRequest,
    MotionPlanApplyPatchResult,
    MotionPlanCompileRequest,
    MotionPlanGenerationRequest,
    MotionPlanMutationResult,
    MotionPlanPatchRequest,
    MotionPlanRead,
    MotionPlanValidationRead,
    MotionPlanWrite,
)
from app.services.project_store import FileProjectStore, ProjectConflictError, ProjectNotFoundError

router = APIRouter(tags=["motion-plans"])
ProjectStoreDep = Annotated[FileProjectStore, Depends(get_project_store)]
JobRunnerDep = Annotated[JobRunner, Depends(get_job_runner)]
PlanServiceDep = Annotated[MotionPlanService, Depends(get_motion_plan_service)]
CompileServiceDep = Annotated[MotionPlanCompileService, Depends(get_motion_plan_compile_service)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]


def _options(
    settings: Settings, temperature: float | None, timeout_seconds: float | None
) -> GenerationOptions:
    return GenerationOptions(
        temperature=temperature if temperature is not None else settings.ollama_temperature,
        keep_alive=settings.ollama_keep_alive,
        timeout_seconds=timeout_seconds
        if timeout_seconds is not None
        else settings.ollama_generation_timeout_seconds,
        num_ctx=settings.ollama_num_ctx,
    )


@router.post(
    "/scenes/{scene_id}/motion-plans/generate",
    response_model=Job,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_motion_plan(
    scene_id: str,
    payload: MotionPlanGenerationRequest,
    runner: JobRunnerDep,
    service: PlanServiceDep,
    settings: SettingsDep,
) -> Job:
    """Start an AI motion-planning job (specs §23.5, returns 202 + a job)."""
    generation_input = MotionPlanGenerationInput(
        scene_id=scene_id,
        expected_revision=payload.expected_revision,
        model=payload.model,
        prompt=payload.prompt,
        use_fixture=payload.use_fixture,
        options=_options(settings, payload.temperature, payload.timeout_seconds),
    )

    async def body(ctx: JobContext) -> MotionPlanGenerationResult:
        return await service.generate(generation_input, ctx)

    return await runner.submit(kind="motion_plan_generation", body=body)


@router.get("/motion-plans/{plan_id}", response_model=MotionPlanRead)
def get_motion_plan(plan_id: str, store: ProjectStoreDep) -> MotionPlanRead:
    try:
        stored = store.get_motion_plan(plan_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="motion plan not found") from exc
    return MotionPlanRead(
        project_id=stored.project_id, plan=stored.plan, revision=stored.revision
    )


@router.patch("/motion-plans/{plan_id}", response_model=MotionPlanMutationResult)
def update_motion_plan(
    plan_id: str,
    payload: MotionPlanWrite,
    store: ProjectStoreDep,
) -> MotionPlanMutationResult:
    """Persist a user edit of the plan (parameters, ordering, style)."""
    if payload.plan.id != plan_id:
        raise HTTPException(status_code=422, detail="plan id does not match route")
    try:
        stored = store.get_motion_plan(plan_id)
        updated = store.save_motion_plan(
            stored.project_id, payload.plan, payload.expected_revision
        )
    except ProjectConflictError as exc:
        raise HTTPException(status_code=409, detail="stale project revision") from exc
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="motion plan not found") from exc
    except DomainValidationError as exc:
        raise HTTPException(
            status_code=422, detail=[asdict(issue) for issue in exc.issues]
        ) from exc
    return MotionPlanMutationResult(document=updated.document, revision=updated.revision)


@router.post("/motion-plans/{plan_id}/validate", response_model=MotionPlanValidationRead)
def validate_motion_plan_route(
    plan_id: str, store: ProjectStoreDep
) -> MotionPlanValidationRead:
    try:
        stored = store.get_motion_plan(plan_id)
        scene = store.get_scene(stored.plan.scene_id)
        project = store.get_project(stored.project_id).document
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="motion plan not found") from exc
    characters = {character.id: character for character in project.characters}
    snapshot = build_scene_snapshot(scene.scene, characters=characters)
    result = validate_motion_plan(stored.plan, snapshot)
    return MotionPlanValidationRead(errors=result.errors, warnings=result.warnings)


@router.post(
    "/motion-plans/{plan_id}/compile",
    response_model=Job,
    status_code=status.HTTP_202_ACCEPTED,
)
async def compile_motion_plan_route(
    plan_id: str,
    payload: MotionPlanCompileRequest,
    runner: JobRunnerDep,
    service: CompileServiceDep,
) -> Job:
    """Start a deterministic compile job for a stored plan (202 + job)."""
    compile_input = MotionPlanCompileInput(
        plan_id=plan_id,
        expected_revision=payload.expected_revision,
        clip_name=payload.clip_name,
    )

    async def body(ctx: JobContext) -> MotionPlanCompileResult:
        return await service.compile(compile_input, ctx)

    return await runner.submit(kind="motion_plan_compile", body=body)


@router.post(
    "/motion-plans/{plan_id}/patch",
    response_model=Job,
    status_code=status.HTTP_202_ACCEPTED,
)
async def patch_motion_plan(
    plan_id: str,
    payload: MotionPlanPatchRequest,
    runner: JobRunnerDep,
    service: PlanServiceDep,
    settings: SettingsDep,
) -> Job:
    """Ask the model for a scoped correction patch; returns a preview job."""
    patch_input = MotionPlanPatchInput(
        plan_id=plan_id,
        expected_revision=payload.expected_revision,
        model=payload.model,
        instruction=payload.instruction,
        action_ids=payload.action_ids,
        time_range=payload.time_range,
        options=_options(settings, payload.temperature, payload.timeout_seconds),
    )

    async def body(ctx: JobContext) -> MotionPlanPatchResult:
        return await service.generate_patch(patch_input, ctx)

    return await runner.submit(kind="motion_plan_patch", body=body)


@router.post(
    "/motion-plans/{plan_id}/apply-patch",
    response_model=MotionPlanApplyPatchResult,
)
def apply_motion_plan_patch(
    plan_id: str,
    payload: MotionPlanApplyPatchRequest,
    store: ProjectStoreDep,
) -> MotionPlanApplyPatchResult:
    """Deterministically apply a previewed patch. Undo by re-saving the
    returned ``previous_plan`` through PATCH /motion-plans/{plan_id}."""
    try:
        stored = store.get_motion_plan(plan_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="motion plan not found") from exc
    application = apply_plan_patch(stored.plan, payload.patch)
    if application.plan is None:
        raise HTTPException(
            status_code=422, detail=[asdict(issue) for issue in application.issues]
        )
    try:
        updated = store.save_motion_plan(
            stored.project_id, application.plan, payload.expected_revision
        )
    except ProjectConflictError as exc:
        raise HTTPException(status_code=409, detail="stale project revision") from exc
    except DomainValidationError as exc:
        raise HTTPException(
            status_code=422, detail=[asdict(issue) for issue in exc.issues]
        ) from exc
    return MotionPlanApplyPatchResult(
        document_revision=updated.revision,
        plan=application.plan,
        previous_plan=stored.plan,
        diff=application.diff,
    )
