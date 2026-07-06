from __future__ import annotations

from functools import lru_cache

from app.application.characters.generate import CharacterGenerationService
from app.application.jobs import JobRunner
from app.application.motion.compile import MotionPlanCompileService
from app.application.motion.planner import MotionPlanService
from app.core.config import Settings, get_settings
from app.core.database import engine
from app.infrastructure.llm.ollama import OllamaProvider
from app.infrastructure.llm.prompt_registry import PromptRegistry
from app.infrastructure.llm.provider import LLMProvider
from app.services.health import HealthService
from app.services.project_store import FileProjectStore

# The job runner holds in-memory job state that must persist across requests, so
# it is a process-wide singleton rather than a per-request dependency.
_JOB_RUNNER = JobRunner()


def get_app_settings() -> Settings:
    return get_settings()


def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    return OllamaProvider(
        base_url=settings.ollama_base_url,
        timeout_seconds=settings.ollama_timeout_seconds,
    )


def get_health_service() -> HealthService:
    return HealthService(
        settings=get_settings(),
        engine=engine,
        llm_provider=get_llm_provider(),
    )


def get_project_store() -> FileProjectStore:
    settings = get_settings()
    return FileProjectStore(settings.asset_store_path)


@lru_cache
def get_prompt_registry() -> PromptRegistry:
    return PromptRegistry()


def get_job_runner() -> JobRunner:
    return _JOB_RUNNER


def get_character_generation_service() -> CharacterGenerationService:
    return CharacterGenerationService(
        provider=get_llm_provider(),
        prompt_registry=get_prompt_registry(),
        store=get_project_store(),
    )


def get_motion_plan_service() -> MotionPlanService:
    return MotionPlanService(
        provider=get_llm_provider(),
        prompt_registry=get_prompt_registry(),
        store=get_project_store(),
    )


def get_motion_plan_compile_service() -> MotionPlanCompileService:
    return MotionPlanCompileService(store=get_project_store())
