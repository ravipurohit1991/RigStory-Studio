from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.domain.character import CharacterDefinition
from app.domain.character_builder import CharacterBuilderRequest, CharacterBuilderResult
from app.schemas.projects import ProjectRead

MAX_MODEL_NAME_LENGTH = 120
MAX_PROMPT_TEXT_LENGTH = 4_000


class CharacterRead(BaseModel):
    project_id: str
    character: CharacterDefinition
    revision: str

    model_config = ConfigDict(frozen=True)


class CharacterWrite(BaseModel):
    character: CharacterDefinition
    expected_revision: str

    model_config = ConfigDict(frozen=True)


class CharacterMutationResult(ProjectRead):
    pass


class CharacterBuilderPresetRead(BaseModel):
    request: CharacterBuilderRequest

    model_config = ConfigDict(frozen=True)


class CharacterBuildRead(CharacterBuilderResult):
    pass


class CharacterGenerationRequest(BaseModel):
    """AI character generation request (Ollama planner -> deterministic builder)."""

    model: str = Field(min_length=1, max_length=MAX_MODEL_NAME_LENGTH)
    expected_revision: str
    description: str = Field(default="", max_length=MAX_PROMPT_TEXT_LENGTH)
    form: CharacterBuilderRequest | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    timeout_seconds: float | None = Field(default=None, gt=0.0)

    model_config = ConfigDict(frozen=True)
