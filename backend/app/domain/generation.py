"""Generation records: the audited history of an AI generation (specs §21.7).

A record captures the original request, model, prompt versions, options, raw and
validated responses, repair attempts, timings, and the validation outcome
(FR-CHAR-005). Records are persisted inside the project document so prompt
content stays with the project under user control and never leaks to ordinary
logs. They are pure data with no framework or provider imports.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.domain.blueprint import CharacterBlueprint
from app.domain.character_builder import BuilderDiagnostic
from app.domain.common import DomainModel
from app.domain.ids import CharacterId, GenerationRecordId, PlanId
from app.domain.motion_plan import MotionPlanPatch

type GenerationKind = Literal["character_blueprint", "motion_plan", "motion_plan_patch"]
type GenerationStatus = Literal["succeeded", "repaired", "failed"]
type GenerationFailureKind = Literal["none", "timeout", "invalid_response", "provider_error"]
type AttemptKind = Literal["initial", "repair"]

ISO_TIMESTAMP = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?$"


class GenerationOptionsRecord(DomainModel):
    temperature: float = Field(ge=0.0, le=2.0)
    keep_alive: str | None = None
    timeout_seconds: float = Field(gt=0.0)
    num_ctx: int | None = Field(default=None, ge=0)


class GenerationTiming(DomainModel):
    total_ms: float | None = None
    load_ms: float | None = None
    prompt_eval_ms: float | None = None
    eval_ms: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class GenerationAttempt(DomainModel):
    index: int = Field(ge=0)
    kind: AttemptKind
    valid: bool
    error_summary: tuple[str, ...] = ()
    raw_response: str = ""


class GenerationRecord(DomainModel):
    id: GenerationRecordId
    kind: GenerationKind = "character_blueprint"
    created_at: str = Field(pattern=ISO_TIMESTAMP)
    character_id: CharacterId | None = None
    plan_id: PlanId | None = None
    model_name: str = Field(min_length=1)
    prompt_ids: tuple[str, ...] = ()
    options: GenerationOptionsRecord
    status: GenerationStatus
    failure_kind: GenerationFailureKind = "none"
    retryable: bool = False
    outcome_detail: str = ""
    attempts: tuple[GenerationAttempt, ...] = ()
    timing: GenerationTiming | None = None
    blueprint: CharacterBlueprint | None = None
    plan_patch: MotionPlanPatch | None = None
    builder_diagnostics: tuple[BuilderDiagnostic, ...] = ()
    warnings: tuple[str, ...] = ()
