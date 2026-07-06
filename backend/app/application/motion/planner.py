"""Motion plan generation and correction use cases (plan.md §8.2, §8.5, §8.6).

Generation: build the scene snapshot, rig capability summaries, and action
catalog -> provider chat with the ``MotionPlanDraft`` JSON schema -> structural
and semantic validation -> one repair retry -> mint the stable plan identity ->
atomic commit with an audit record. The model only ever produces the semantic
plan; the deterministic compiler produces every keyframe.

Correction: a scoped instruction plus the current plan produce a
``MotionPlanPatch`` against stable action ids. The patch is validated by
actually applying it to a copy of the plan; applying it for real is a separate
deterministic endpoint so the user can preview and undo.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.application.characters.generate import (
    GenerationConflict,
    GenerationInvalidResponse,
    GenerationProviderFailure,
    GenerationSafetyRefusal,
    GenerationTimeout,
    summarize_validation_error,
    timing_from_result,
)
from app.application.jobs import JobContext
from app.domain.blueprint import scan_prompt_safety
from app.domain.canonical import JsonValue, canonical_json_dumps, model_canonical_json
from app.domain.generation import (
    GenerationAttempt,
    GenerationOptionsRecord,
    GenerationRecord,
    GenerationStatus,
)
from app.domain.ids import new_generation_record_id, new_plan_id
from app.domain.motion_plan import (
    CANNED_HANDSHAKE_PLAN_DRAFT,
    CANNED_MOTION_PLAN_DRAFT,
    MotionPlan,
    MotionPlanDraft,
    MotionPlanPatch,
    PlanWarning,
    action_catalog_text,
    apply_plan_patch,
    build_actor_capabilities,
)
from app.domain.motion_plan_validation import (
    PlanValidationResult,
    summarize_issues,
    validate_motion_plan,
)
from app.domain.scene import SceneDefinition
from app.domain.scene_snapshot import SceneSnapshot, build_scene_snapshot
from app.infrastructure.llm.prompt_registry import (
    MOTION_PLAN_SYSTEM,
    MOTION_PLAN_USER,
    PLAN_PATCH_SYSTEM,
    PLAN_PATCH_USER,
    REPAIR_JSON_SYSTEM,
    PromptRegistry,
)
from app.infrastructure.llm.provider import (
    ChatMessage,
    ChatResult,
    GenerationOptions,
    LLMProvider,
    ProviderError,
    ProviderTimeoutError,
)
from app.services.project_store import (
    FileProjectStore,
    ProjectConflictError,
    ProjectNotFoundError,
)

MAX_ERROR_SUMMARY = 8


class MotionPlanGenerationInput(BaseModel):
    scene_id: str
    expected_revision: str
    model: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    # Developer option (plan.md §10): use the deterministic canned draft
    # instead of calling the model.
    use_fixture: bool = False
    options: GenerationOptions = GenerationOptions()

    model_config = ConfigDict(frozen=True)


class MotionPlanGenerationResult(BaseModel):
    plan_id: str
    record_id: str
    revision: str
    status: GenerationStatus
    model_name: str
    plan: MotionPlan

    model_config = ConfigDict(frozen=True)


class MotionPlanPatchInput(BaseModel):
    plan_id: str
    expected_revision: str
    model: str = Field(min_length=1)
    instruction: str = Field(min_length=1)
    action_ids: tuple[str, ...] = ()
    time_range: tuple[float, float] | None = None
    options: GenerationOptions = GenerationOptions()

    model_config = ConfigDict(frozen=True)


class MotionPlanPatchResult(BaseModel):
    plan_id: str
    record_id: str
    revision: str
    status: GenerationStatus
    model_name: str
    patch: MotionPlanPatch
    patched_plan: MotionPlan
    diff: tuple[str, ...]

    model_config = ConfigDict(frozen=True)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _parse_json_object(raw: str) -> tuple[dict[str, JsonValue] | None, tuple[str, ...]]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, (f"JSON_DECODE_ERROR: {exc}",)
    if not isinstance(data, dict):
        return None, ("JSON_NOT_OBJECT: top-level value is not an object",)
    return data, ()


def _validate_draft(
    raw: str, snapshot: SceneSnapshot
) -> tuple[MotionPlanDraft | None, tuple[str, ...]]:
    """Parse and validate raw model text as a safe plan draft (specs §21.5)."""
    data, errors = _parse_json_object(raw)
    if data is None:
        return None, errors
    try:
        draft = MotionPlanDraft.model_validate(data)
    except ValidationError as exc:
        return None, summarize_validation_error(exc)
    result = validate_motion_plan(draft, snapshot)
    if result.errors:
        return None, summarize_issues(result.errors)[:MAX_ERROR_SUMMARY]
    return draft, ()


def _merge_warnings(
    draft_warnings: tuple[PlanWarning, ...], validation: PlanValidationResult
) -> tuple[PlanWarning, ...]:
    merged: list[PlanWarning] = list(draft_warnings)
    seen = {(warning.code, warning.message) for warning in merged}
    for warning in validation.warnings:
        if (warning.code, warning.message) not in seen:
            merged.append(warning)
            seen.add((warning.code, warning.message))
    return tuple(merged)


def canned_plan_draft_for_scene(snapshot: SceneSnapshot, prompt: str = "") -> MotionPlanDraft:
    """Retarget the deterministic canned draft to the scene's stable ids.

    Enables the developer fixture path on any scene that has the
    required affordances; validation still rejects scenes it cannot fit. A
    two-actor scene with a shake-like prompt gets the handshake fixture.
    """
    actor_ids = [actor.id for actor in snapshot.actors]
    sit_anchor = next(
        (
            affordance.anchor_ref
            for scene_object in snapshot.objects
            for affordance in scene_object.affordances
            if affordance.type == "sit" and affordance.anchor_ref is not None
        ),
        None,
    )
    if len(actor_ids) >= 2 and "shake" in prompt.lower():
        draft = CANNED_HANDSHAKE_PLAN_DRAFT
        look_target = next(
            (
                scene_object.id
                for scene_object in snapshot.objects
                if any(affordance.type == "look_at" for affordance in scene_object.affordances)
            ),
            snapshot.objects[0].id if snapshot.objects else actor_ids[0],
        )
        replacements = {
            "actor_mira": actor_ids[0],
            "actor_jon": actor_ids[1],
            "door_main": look_target,
        }
    else:
        draft = CANNED_MOTION_PLAN_DRAFT
        replacements = {
            "actor_mira": actor_ids[0] if actor_ids else "actor_missing",
            "chair_main.seat": sit_anchor or "chair_main.seat",
        }
    # Two-phase substitution so overlapping old/new ids never chain into each
    # other (for example swapping the two actor ids).
    raw = model_canonical_json(draft)
    for index, old in enumerate(replacements):
        raw = raw.replace(f'"{old}"', f'"__fixture_{index}__"')
    for index, new in enumerate(replacements.values()):
        raw = raw.replace(f'"__fixture_{index}__"', f'"{new}"')
    return MotionPlanDraft.model_validate_json(raw)


class MotionPlanService:
    def __init__(
        self,
        *,
        provider: LLMProvider,
        prompt_registry: PromptRegistry,
        store: FileProjectStore,
    ) -> None:
        self._provider = provider
        self._prompt_registry = prompt_registry
        self._store = store

    async def _chat(
        self,
        model: str,
        messages: list[ChatMessage],
        options: GenerationOptions,
        schema: dict[str, JsonValue],
    ) -> ChatResult:
        try:
            return await self._provider.chat(
                model=model,
                messages=messages,
                options=options,
                format_schema=schema,
            )
        except ProviderTimeoutError as exc:
            raise GenerationTimeout(str(exc)) from exc
        except ProviderError as exc:
            raise GenerationProviderFailure(str(exc)) from exc

    def _repair_messages(
        self, previous_raw: str, errors: tuple[str, ...], schema_text: str
    ) -> list[ChatMessage]:
        system = self._prompt_registry.render(REPAIR_JSON_SYSTEM)
        error_lines = "\n".join(f"- {error}" for error in errors)
        user = (
            f"Previous JSON you returned:\n{previous_raw}\n\n"
            f"Validation errors to fix:\n{error_lines}\n\n"
            f"Return corrected JSON conforming to this schema:\n{schema_text}"
        )
        return [
            ChatMessage(role="system", content=system),
            ChatMessage(role="user", content=user),
        ]

    def _options_record(self, options: GenerationOptions) -> GenerationOptionsRecord:
        return GenerationOptionsRecord(
            temperature=options.temperature,
            keep_alive=options.keep_alive,
            timeout_seconds=options.timeout_seconds,
            num_ctx=options.num_ctx,
        )

    async def generate(
        self,
        input_: MotionPlanGenerationInput,
        ctx: JobContext | None = None,
    ) -> MotionPlanGenerationResult:
        async def report(stage: str, message: str, fraction: float | None) -> None:
            if ctx is not None:
                await ctx.progress(stage, message, fraction)

        unsafe = scan_prompt_safety(input_.prompt)
        if unsafe is not None:
            raise GenerationSafetyRefusal(
                f"The request cannot be planned: it contains disallowed content ({unsafe!r})."
            )

        try:
            stored_scene = self._store.get_scene(input_.scene_id)
            project = self._store.get_project(stored_scene.project_id).document
        except ProjectNotFoundError as exc:
            raise GenerationConflict(f"scene {input_.scene_id!r} not found") from exc
        scene: SceneDefinition = stored_scene.scene
        characters = {character.id: character for character in project.characters}
        snapshot = build_scene_snapshot(scene, characters=characters)
        capabilities = build_actor_capabilities(scene, characters)

        schema: dict[str, JsonValue] = MotionPlanDraft.model_json_schema()
        schema_text = canonical_json_dumps(schema)
        attempts: list[GenerationAttempt] = []
        status: GenerationStatus = "succeeded"

        await report("planning", "Requesting a motion plan from the model.", 0.1)
        if input_.use_fixture:
            draft = canned_plan_draft_for_scene(snapshot, input_.prompt)
            fixture_errors = validate_motion_plan(draft, snapshot).errors
            if fixture_errors:
                raise GenerationInvalidResponse(
                    "The canned fixture plan does not fit this scene: "
                    + "; ".join(summarize_issues(fixture_errors)),
                    (),
                )
            model_name = "fixture"
            timing = None
        else:
            system = self._prompt_registry.render(MOTION_PLAN_SYSTEM)
            user = self._prompt_registry.render(
                MOTION_PLAN_USER,
                prompt=input_.prompt,
                snapshot=snapshot.canonical_json(),
                rig_summary="\n".join(
                    model_canonical_json(capability) for capability in capabilities
                ),
                action_catalog=action_catalog_text(),
                schema=schema_text,
            )
            messages = [
                ChatMessage(role="system", content=system),
                ChatMessage(role="user", content=user),
            ]
            result = await self._chat(input_.model, messages, input_.options, schema)
            maybe_draft, errors = _validate_draft(result.content, snapshot)
            attempts.append(
                GenerationAttempt(
                    index=0,
                    kind="initial",
                    valid=maybe_draft is not None,
                    error_summary=errors,
                    raw_response=result.content,
                )
            )
            if maybe_draft is None:
                await report("repair", "The first plan was invalid; requesting a repair.", 0.4)
                repair_result = await self._chat(
                    input_.model,
                    self._repair_messages(result.content, errors, schema_text),
                    input_.options,
                    schema,
                )
                maybe_draft, repair_errors = _validate_draft(repair_result.content, snapshot)
                attempts.append(
                    GenerationAttempt(
                        index=1,
                        kind="repair",
                        valid=maybe_draft is not None,
                        error_summary=repair_errors,
                        raw_response=repair_result.content,
                    )
                )
                if maybe_draft is None:
                    raise GenerationInvalidResponse(
                        "The model plan failed validation after one repair attempt.",
                        tuple(attempts),
                    )
                result = repair_result
                status = "repaired"
            draft = maybe_draft
            model_name = result.model or input_.model
            timing = timing_from_result(result)

        await report("validating", "Validating the plan against the scene.", 0.7)
        plan = MotionPlan.model_validate(
            {
                **draft.model_dump(mode="python"),
                "id": new_plan_id(),
                "scene_id": scene.id,
                "prompt": input_.prompt,
                "created_at": _now_iso(),
            }
        )
        validation = validate_motion_plan(plan, snapshot)
        if validation.errors:
            raise GenerationInvalidResponse(
                "The plan failed scene validation: "
                + "; ".join(summarize_issues(validation.errors)),
                tuple(attempts),
            )
        plan = plan.model_copy(update={"warnings": _merge_warnings(plan.warnings, validation)})

        record = GenerationRecord(
            id=new_generation_record_id(),
            kind="motion_plan",
            created_at=_now_iso(),
            plan_id=plan.id,
            model_name=model_name,
            prompt_ids=self._generation_prompt_ids(status, input_.use_fixture),
            options=self._options_record(input_.options),
            status=status,
            outcome_detail=(
                "Validated on the first attempt."
                if status == "succeeded"
                else "Validated after one repair attempt."
            ),
            attempts=tuple(attempts),
            timing=timing,
            warnings=tuple(warning.message for warning in plan.warnings),
        )

        await report("saving", "Committing the plan and generation record.", 0.9)
        try:
            stored = self._store.commit_motion_plan(
                stored_scene.project_id, plan, record, input_.expected_revision
            )
        except ProjectConflictError as exc:
            raise GenerationConflict(
                "The project changed since planning started; nothing was saved."
            ) from exc
        except ProjectNotFoundError as exc:
            raise GenerationConflict(f"project {stored_scene.project_id!r} not found") from exc

        await report("done", "Motion plan generated.", 1.0)
        return MotionPlanGenerationResult(
            plan_id=plan.id,
            record_id=record.id,
            revision=stored.revision,
            status=status,
            model_name=model_name,
            plan=plan,
        )

    async def generate_patch(
        self,
        input_: MotionPlanPatchInput,
        ctx: JobContext | None = None,
    ) -> MotionPlanPatchResult:
        async def report(stage: str, message: str, fraction: float | None) -> None:
            if ctx is not None:
                await ctx.progress(stage, message, fraction)

        unsafe = scan_prompt_safety(input_.instruction)
        if unsafe is not None:
            raise GenerationSafetyRefusal(
                f"The correction cannot be applied: it contains disallowed content ({unsafe!r})."
            )

        try:
            stored_plan = self._store.get_motion_plan(input_.plan_id)
            project = self._store.get_project(stored_plan.project_id).document
            stored_scene = self._store.get_scene(stored_plan.plan.scene_id)
        except ProjectNotFoundError as exc:
            raise GenerationConflict(f"plan {input_.plan_id!r} not found") from exc
        plan = stored_plan.plan
        characters = {character.id: character for character in project.characters}
        snapshot = build_scene_snapshot(stored_scene.scene, characters=characters)

        schema: dict[str, JsonValue] = MotionPlanPatch.model_json_schema()
        schema_text = canonical_json_dumps(schema)
        selection_parts: list[str] = []
        if input_.action_ids:
            selection_parts.append(f"action ids: {', '.join(input_.action_ids)}")
        if input_.time_range is not None:
            selection_parts.append(
                f"time range: {input_.time_range[0]}s to {input_.time_range[1]}s"
            )
        selection = "; ".join(selection_parts) or "the whole plan"

        def validate_patch_raw(
            raw: str,
        ) -> tuple[tuple[MotionPlanPatch, MotionPlan, tuple[str, ...]] | None, tuple[str, ...]]:
            data, parse_errors = _parse_json_object(raw)
            if data is None:
                return None, parse_errors
            try:
                patch = MotionPlanPatch.model_validate(data)
            except ValidationError as exc:
                return None, summarize_validation_error(exc)
            application = apply_plan_patch(plan, patch)
            if application.plan is None:
                return None, summarize_issues(application.issues)[:MAX_ERROR_SUMMARY]
            semantic = validate_motion_plan(application.plan, snapshot)
            if semantic.errors:
                return None, summarize_issues(semantic.errors)[:MAX_ERROR_SUMMARY]
            return (patch, application.plan, application.diff), ()

        await report("patching", "Requesting a plan patch from the model.", 0.1)
        user = self._prompt_registry.render(
            PLAN_PATCH_USER,
            instruction=input_.instruction,
            selection=selection,
            plan_json=model_canonical_json(plan),
            schema=schema_text,
        )
        messages = [
            ChatMessage(role="system", content=self._prompt_registry.render(PLAN_PATCH_SYSTEM)),
            ChatMessage(role="user", content=user),
        ]
        result = await self._chat(input_.model, messages, input_.options, schema)
        validated, errors = validate_patch_raw(result.content)
        attempts = [
            GenerationAttempt(
                index=0,
                kind="initial",
                valid=validated is not None,
                error_summary=errors,
                raw_response=result.content,
            )
        ]
        status: GenerationStatus = "succeeded"
        if validated is None:
            await report("repair", "The first patch was invalid; requesting a repair.", 0.4)
            repair_result = await self._chat(
                input_.model,
                self._repair_messages(result.content, errors, schema_text),
                input_.options,
                schema,
            )
            validated, repair_errors = validate_patch_raw(repair_result.content)
            attempts.append(
                GenerationAttempt(
                    index=1,
                    kind="repair",
                    valid=validated is not None,
                    error_summary=repair_errors,
                    raw_response=repair_result.content,
                )
            )
            if validated is None:
                raise GenerationInvalidResponse(
                    "The model patch failed validation after one repair attempt.",
                    tuple(attempts),
                )
            result = repair_result
            status = "repaired"
        patch, patched_plan, diff = validated

        record = GenerationRecord(
            id=new_generation_record_id(),
            kind="motion_plan_patch",
            created_at=_now_iso(),
            plan_id=plan.id,
            model_name=result.model or input_.model,
            prompt_ids=self._patch_prompt_ids(status),
            options=self._options_record(input_.options),
            status=status,
            outcome_detail=(
                "Patch validated on the first attempt."
                if status == "succeeded"
                else "Patch validated after one repair attempt."
            ),
            attempts=tuple(attempts),
            timing=timing_from_result(result),
            plan_patch=patch,
            warnings=tuple(warning.message for warning in patch.warnings),
        )

        await report("saving", "Committing the patch audit record.", 0.9)
        try:
            stored = self._store.commit_generation_record(
                stored_plan.project_id, record, input_.expected_revision
            )
        except ProjectConflictError as exc:
            raise GenerationConflict(
                "The project changed since the correction started; nothing was saved."
            ) from exc
        except ProjectNotFoundError as exc:
            raise GenerationConflict(f"project {stored_plan.project_id!r} not found") from exc

        await report("done", "Plan patch generated; review and apply it.", 1.0)
        return MotionPlanPatchResult(
            plan_id=plan.id,
            record_id=record.id,
            revision=stored.revision,
            status=status,
            model_name=result.model or input_.model,
            patch=patch,
            patched_plan=patched_plan,
            diff=diff,
        )

    @staticmethod
    def _generation_prompt_ids(status: GenerationStatus, use_fixture: bool) -> tuple[str, ...]:
        if use_fixture:
            return ()
        base = (MOTION_PLAN_SYSTEM, MOTION_PLAN_USER)
        if status == "repaired":
            return (*base, REPAIR_JSON_SYSTEM)
        return base

    @staticmethod
    def _patch_prompt_ids(status: GenerationStatus) -> tuple[str, ...]:
        base = (PLAN_PATCH_SYSTEM, PLAN_PATCH_USER)
        if status == "repaired":
            return (*base, REPAIR_JSON_SYSTEM)
        return base
