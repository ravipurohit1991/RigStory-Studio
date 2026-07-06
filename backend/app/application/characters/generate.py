"""Character generation use case (plan.md §5.2, §5.4).

Orchestrates: build prompt -> provider chat with a JSON schema -> validate ->
one repair retry -> deterministic map+build -> atomic commit with an audit
record. The LLM only produces the validated :class:`CharacterBlueprint`; the
deterministic builder produces the rig and art (specs §2.2).

Failures are classified so the API can distinguish retryable transport/timeout
problems from a genuinely invalid model response, and a failed generation never
mutates project state.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.application.jobs import JobContext, JobFailure
from app.domain.blueprint import (
    CharacterBlueprint,
    FieldProvenance,
    blueprint_to_builder_request,
    scan_prompt_safety,
    validate_character_blueprint,
)
from app.domain.canonical import JsonValue, canonical_json_dumps
from app.domain.character_builder import (
    BuilderDiagnostic,
    CharacterBuilderRequest,
    build_procedural_character,
)
from app.domain.generation import (
    GenerationAttempt,
    GenerationOptionsRecord,
    GenerationRecord,
    GenerationStatus,
    GenerationTiming,
)
from app.domain.ids import new_character_id, new_generation_record_id
from app.infrastructure.llm.prompt_registry import (
    CHARACTER_BLUEPRINT_SYSTEM,
    CHARACTER_BLUEPRINT_USER,
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
from app.services.project_store import FileProjectStore, ProjectConflictError, ProjectNotFoundError

MAX_ERROR_SUMMARY = 8


class GenerationTimeout(JobFailure):
    def __init__(self, message: str) -> None:
        super().__init__(message, kind="timeout", retryable=True)


class GenerationProviderFailure(JobFailure):
    def __init__(self, message: str) -> None:
        super().__init__(message, kind="provider_error", retryable=True)


class GenerationSafetyRefusal(JobFailure):
    def __init__(self, message: str) -> None:
        super().__init__(message, kind="safety", retryable=False)


class GenerationInvalidResponse(JobFailure):
    def __init__(self, message: str, attempts: tuple[GenerationAttempt, ...]) -> None:
        detail: dict[str, JsonValue] = {
            "attempts": [attempt.model_dump(mode="json") for attempt in attempts]
        }
        super().__init__(message, kind="invalid_response", retryable=False, detail=detail)


class GenerationConflict(JobFailure):
    def __init__(self, message: str) -> None:
        super().__init__(message, kind="conflict", retryable=False)


class CharacterGenerationInput(BaseModel):
    project_id: str
    expected_revision: str
    model: str = Field(min_length=1)
    description: str = ""
    form: CharacterBuilderRequest | None = None
    options: GenerationOptions = GenerationOptions()

    model_config = ConfigDict(frozen=True)


class CharacterGenerationResult(BaseModel):
    character_id: str
    record_id: str
    revision: str
    status: GenerationStatus
    model_name: str
    blueprint: CharacterBlueprint
    request: CharacterBuilderRequest
    provenance: tuple[FieldProvenance, ...]
    builder_diagnostics: tuple[BuilderDiagnostic, ...]
    warnings: tuple[str, ...]

    model_config = ConfigDict(frozen=True)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _ns_to_ms(value: int | None) -> float | None:
    return round(value / 1_000_000, 3) if value is not None else None


def timing_from_result(result: ChatResult) -> GenerationTiming:
    return GenerationTiming(
        total_ms=_ns_to_ms(result.total_duration_ns),
        load_ms=_ns_to_ms(result.load_duration_ns),
        prompt_eval_ms=_ns_to_ms(result.prompt_eval_duration_ns),
        eval_ms=_ns_to_ms(result.eval_duration_ns),
        prompt_tokens=result.prompt_eval_count,
        completion_tokens=result.eval_count,
    )


def summarize_validation_error(exc: ValidationError) -> tuple[str, ...]:
    summary = [
        f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}" for error in exc.errors()
    ]
    return tuple(summary[:MAX_ERROR_SUMMARY])


def _validate_raw(raw: str) -> tuple[CharacterBlueprint | None, tuple[str, ...]]:
    """Parse and validate raw model text as a safe blueprint (specs §21.5)."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, (f"JSON_DECODE_ERROR: {exc}",)
    if not isinstance(data, dict):
        return None, ("JSON_NOT_OBJECT: top-level value is not an object",)
    try:
        blueprint = CharacterBlueprint.model_validate(data)
    except ValidationError as exc:
        return None, summarize_validation_error(exc)
    issues = validate_character_blueprint(blueprint)
    if issues:
        return None, tuple(str(issue) for issue in issues)[:MAX_ERROR_SUMMARY]
    return blueprint, ()


class CharacterGenerationService:
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

    def _schema_text(self) -> str:
        schema: JsonValue = CharacterBlueprint.model_json_schema()
        return canonical_json_dumps(schema)

    def _form_summary(self, form: CharacterBuilderRequest | None) -> str:
        if form is None:
            return "None provided; choose reasonable values."
        fields = form.model_dump(mode="json")
        return "\n".join(f"- {key}: {value}" for key, value in sorted(fields.items()))

    def _initial_messages(self, input_: CharacterGenerationInput) -> list[ChatMessage]:
        system = self._prompt_registry.render(CHARACTER_BLUEPRINT_SYSTEM)
        user = self._prompt_registry.render(
            CHARACTER_BLUEPRINT_USER,
            description=input_.description or "No free-text description provided.",
            form_summary=self._form_summary(input_.form),
            schema=self._schema_text(),
        )
        return [
            ChatMessage(role="system", content=system),
            ChatMessage(role="user", content=user),
        ]

    def _repair_messages(self, previous_raw: str, errors: tuple[str, ...]) -> list[ChatMessage]:
        system = self._prompt_registry.render(REPAIR_JSON_SYSTEM)
        error_lines = "\n".join(f"- {error}" for error in errors)
        user = (
            f"Previous JSON you returned:\n{previous_raw}\n\n"
            f"Validation errors to fix:\n{error_lines}\n\n"
            f"Return corrected JSON conforming to this schema:\n{self._schema_text()}"
        )
        return [
            ChatMessage(role="system", content=system),
            ChatMessage(role="user", content=user),
        ]

    async def _chat(
        self, model: str, messages: list[ChatMessage], options: GenerationOptions
    ) -> ChatResult:
        schema: dict[str, JsonValue] = CharacterBlueprint.model_json_schema()
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

    async def generate(
        self,
        input_: CharacterGenerationInput,
        ctx: JobContext | None = None,
    ) -> CharacterGenerationResult:
        async def report(stage: str, message: str, fraction: float | None) -> None:
            if ctx is not None:
                await ctx.progress(stage, message, fraction)

        unsafe = scan_prompt_safety(input_.description)
        if unsafe is not None:
            raise GenerationSafetyRefusal(
                f"The request cannot be generated: it contains disallowed content ({unsafe!r})."
            )

        # Fail fast on a stale revision before spending an LLM call.
        try:
            self._store.get_project(input_.project_id)
        except ProjectNotFoundError as exc:
            raise GenerationConflict(f"project {input_.project_id!r} not found") from exc

        await report("planning", "Requesting a character blueprint from the model.", 0.1)
        attempts: list[GenerationAttempt] = []
        final_result = await self._chat(
            input_.model, self._initial_messages(input_), input_.options
        )
        blueprint, errors = _validate_raw(final_result.content)
        attempts.append(
            GenerationAttempt(
                index=0,
                kind="initial",
                valid=blueprint is not None,
                error_summary=errors,
                raw_response=final_result.content,
            )
        )

        status: GenerationStatus = "succeeded"
        if blueprint is None:
            await report("repair", "The first response was invalid; requesting a repair.", 0.4)
            repair_result = await self._chat(
                input_.model, self._repair_messages(final_result.content, errors), input_.options
            )
            repaired, repair_errors = _validate_raw(repair_result.content)
            attempts.append(
                GenerationAttempt(
                    index=1,
                    kind="repair",
                    valid=repaired is not None,
                    error_summary=repair_errors,
                    raw_response=repair_result.content,
                )
            )
            if repaired is None:
                raise GenerationInvalidResponse(
                    "The model response failed schema validation after one repair attempt.",
                    tuple(attempts),
                )
            blueprint = repaired
            final_result = repair_result
            status = "repaired"

        await report("building", "Building the rig and vector art deterministically.", 0.7)
        mapping = blueprint_to_builder_request(blueprint)
        built = build_procedural_character(mapping.request)
        character = built.character.model_copy(update={"id": new_character_id()})

        record = GenerationRecord(
            id=new_generation_record_id(),
            created_at=_now_iso(),
            character_id=character.id,
            model_name=final_result.model or input_.model,
            prompt_ids=self._prompt_ids(status),
            options=GenerationOptionsRecord(
                temperature=input_.options.temperature,
                keep_alive=input_.options.keep_alive,
                timeout_seconds=input_.options.timeout_seconds,
                num_ctx=input_.options.num_ctx,
            ),
            status=status,
            outcome_detail=(
                "Validated on the first attempt."
                if status == "succeeded"
                else "Validated after one repair attempt."
            ),
            attempts=tuple(attempts),
            timing=timing_from_result(final_result),
            blueprint=blueprint,
            builder_diagnostics=built.diagnostics,
            warnings=(*blueprint.warnings, *mapping.warnings),
        )

        await report("saving", "Committing the character and generation record.", 0.9)
        try:
            stored = self._store.commit_generated_character(
                input_.project_id, character, record, input_.expected_revision
            )
        except ProjectConflictError as exc:
            raise GenerationConflict(
                "The project changed since generation started; nothing was saved."
            ) from exc
        except ProjectNotFoundError as exc:
            raise GenerationConflict(f"project {input_.project_id!r} not found") from exc

        await report("done", "Character generated.", 1.0)
        return CharacterGenerationResult(
            character_id=character.id,
            record_id=record.id,
            revision=stored.revision,
            status=status,
            model_name=record.model_name,
            blueprint=blueprint,
            request=built.normalized_request,
            provenance=mapping.provenance,
            builder_diagnostics=built.diagnostics,
            warnings=record.warnings,
        )

    @staticmethod
    def _prompt_ids(status: GenerationStatus) -> tuple[str, ...]:
        base = (CHARACTER_BLUEPRINT_SYSTEM, CHARACTER_BLUEPRINT_USER)
        if status == "repaired":
            return (*base, REPAIR_JSON_SYSTEM)
        return base
