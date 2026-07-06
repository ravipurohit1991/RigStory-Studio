from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.domain.errors import ValidationIssue
from app.domain.motion_plan import MotionPlan, MotionPlanPatch, PlanWarning
from app.schemas.projects import ProjectRead

MAX_MODEL_NAME_LENGTH = 120
MAX_PROMPT_TEXT_LENGTH = 4_000


class MotionPlanGenerationRequest(BaseModel):
    """AI motion planning request (Ollama planner -> deterministic compiler)."""

    model: str = Field(min_length=1, max_length=MAX_MODEL_NAME_LENGTH)
    expected_revision: str
    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_TEXT_LENGTH)
    use_fixture: bool = False
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    timeout_seconds: float | None = Field(default=None, gt=0.0)

    model_config = ConfigDict(frozen=True)


class MotionPlanRead(BaseModel):
    project_id: str
    plan: MotionPlan
    revision: str

    model_config = ConfigDict(frozen=True)


class MotionPlanWrite(BaseModel):
    plan: MotionPlan
    expected_revision: str

    model_config = ConfigDict(frozen=True)


class MotionPlanMutationResult(ProjectRead):
    pass


class MotionPlanValidationRead(BaseModel):
    errors: tuple[ValidationIssue, ...]
    warnings: tuple[PlanWarning, ...]

    model_config = ConfigDict(frozen=True)


class MotionPlanCompileRequest(BaseModel):
    expected_revision: str
    clip_name: str = Field(default="Planned motion", min_length=1)

    model_config = ConfigDict(frozen=True)


class MotionPlanPatchRequest(BaseModel):
    """Ask the model for a scoped correction patch (plan.md §8.6)."""

    model: str = Field(min_length=1, max_length=MAX_MODEL_NAME_LENGTH)
    expected_revision: str
    instruction: str = Field(min_length=1, max_length=MAX_PROMPT_TEXT_LENGTH)
    action_ids: tuple[str, ...] = ()
    time_range: tuple[float, float] | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    timeout_seconds: float | None = Field(default=None, gt=0.0)

    model_config = ConfigDict(frozen=True)


class MotionPlanApplyPatchRequest(BaseModel):
    """Deterministically apply a previously generated and previewed patch."""

    patch: MotionPlanPatch
    expected_revision: str

    model_config = ConfigDict(frozen=True)


class MotionPlanApplyPatchResult(BaseModel):
    document_revision: str
    plan: MotionPlan
    previous_plan: MotionPlan
    diff: tuple[str, ...]

    model_config = ConfigDict(frozen=True)
