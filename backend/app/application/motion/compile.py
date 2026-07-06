"""Motion plan compile job (plan.md §8.5).

Deterministic: no model is involved. Resolves the stored plan against its
scene, reports stage progress, compiles through the deterministic engine, and
commits the clip atomically. The clip is linked to its source plan and engine
version, and a recompile after a plan edit reuses the same clip id so timeline
references survive.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.application.characters.generate import GenerationConflict
from app.application.jobs import JobContext, JobFailure
from app.domain.canonical import JsonValue
from app.domain.ids import new_clip_id
from app.domain.motion import MotionValidationReport
from app.domain.motion_plan_validation import summarize_issues, validate_motion_plan
from app.domain.plan_compiler import compile_motion_plan
from app.domain.scene_snapshot import build_scene_snapshot
from app.services.project_store import (
    FileProjectStore,
    ProjectConflictError,
    ProjectNotFoundError,
)


class PlanCompileFailure(JobFailure):
    def __init__(self, message: str, issues: tuple[str, ...] = ()) -> None:
        detail: dict[str, JsonValue] = {"issues": list(issues)}
        super().__init__(message, kind="invalid_plan", retryable=False, detail=detail)


class MotionPlanCompileInput(BaseModel):
    plan_id: str
    expected_revision: str
    clip_name: str = Field(default="Planned motion", min_length=1)

    model_config = ConfigDict(frozen=True)


class MotionPlanCompileResult(BaseModel):
    plan_id: str
    clip_id: str
    revision: str
    engine_version: str
    report: MotionValidationReport

    model_config = ConfigDict(frozen=True)


class MotionPlanCompileService:
    def __init__(self, *, store: FileProjectStore) -> None:
        self._store = store

    async def compile(
        self,
        input_: MotionPlanCompileInput,
        ctx: JobContext | None = None,
    ) -> MotionPlanCompileResult:
        async def report(stage: str, message: str, fraction: float | None) -> None:
            if ctx is not None:
                await ctx.progress(stage, message, fraction)

        await report("resolve", "Loading the plan and scene.", 0.1)
        try:
            stored_plan = self._store.get_motion_plan(input_.plan_id)
            project = self._store.get_project(stored_plan.project_id).document
        except ProjectNotFoundError as exc:
            raise GenerationConflict(f"plan {input_.plan_id!r} not found") from exc
        plan = stored_plan.plan
        scene = next(
            (candidate for candidate in project.scenes if candidate.id == plan.scene_id), None
        )
        if scene is None:
            raise PlanCompileFailure(f"plan scene {plan.scene_id!r} no longer exists")
        characters = {character.id: character for character in project.characters}

        await report("schedule", "Validating the plan and resolving the schedule.", 0.3)
        snapshot = build_scene_snapshot(scene, characters=characters)
        validation = validate_motion_plan(plan, snapshot)
        if validation.errors:
            raise PlanCompileFailure(
                "The plan is not compilable against the current scene.",
                summarize_issues(validation.errors),
            )

        # Recompiles keep the clip id linked to this plan stable.
        existing_clip_id = next(
            (clip.id for clip in project.clips if clip.source_plan_id == plan.id), None
        )
        clip_id = existing_clip_id or new_clip_id()

        await report("solve", "Compiling deterministic motion.", 0.6)
        compiled = compile_motion_plan(
            scene=scene,
            characters=characters,
            plan=plan,
            clip_id=clip_id,
            clip_name=input_.clip_name,
        )

        await report("commit", "Committing the clip.", 0.9)
        try:
            stored = self._store.commit_compiled_clip(
                stored_plan.project_id, compiled.clip, input_.expected_revision
            )
        except ProjectConflictError as exc:
            raise GenerationConflict(
                "The project changed since compilation started; nothing was saved."
            ) from exc
        except ProjectNotFoundError as exc:
            raise GenerationConflict(f"project {stored_plan.project_id!r} not found") from exc

        await report("done", "Clip compiled.", 1.0)
        return MotionPlanCompileResult(
            plan_id=plan.id,
            clip_id=compiled.clip.id,
            revision=stored.revision,
            engine_version=compiled.engine_version,
            report=compiled.report,
        )
