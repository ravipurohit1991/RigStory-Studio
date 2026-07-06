from __future__ import annotations

from pathlib import Path

import pytest

from app.application.characters.generate import (
    CharacterGenerationInput,
    CharacterGenerationService,
    GenerationConflict,
    GenerationInvalidResponse,
    GenerationSafetyRefusal,
    GenerationTimeout,
)
from app.domain.blueprint import CANNED_BLUEPRINT
from app.infrastructure.llm.mock import ScriptedLLMProvider, content_result, model_result
from app.infrastructure.llm.prompt_registry import PromptRegistry
from app.infrastructure.llm.provider import ProviderTimeoutError
from app.services.project_store import FileProjectStore


def _service(provider: ScriptedLLMProvider, store: FileProjectStore) -> CharacterGenerationService:
    return CharacterGenerationService(
        provider=provider, prompt_registry=PromptRegistry(), store=store
    )


def _new_project(store: FileProjectStore) -> tuple[str, str]:
    stored = store.create_project(name="Gen")
    return stored.document.project.id, stored.revision


async def test_generation_success_commits_character_and_record(tmp_path: Path) -> None:
    store = FileProjectStore(tmp_path)
    project_id, revision = _new_project(store)
    provider = ScriptedLLMProvider([model_result(CANNED_BLUEPRINT)])
    service = _service(provider, store)

    result = await service.generate(
        CharacterGenerationInput(
            project_id=project_id,
            expected_revision=revision,
            model="planner",
            description="a calm adult woman",
        )
    )

    assert result.status == "succeeded"
    # The deterministic builder, not the model, produced rig and art (specs §2.2).
    document = store.get_project(project_id).document
    assert len(document.characters) == 1
    character = document.characters[0]
    assert character.id == result.character_id
    assert len(character.rig.bones) == 25
    assert character.attachments
    # A structured-output schema was sent to the provider.
    assert provider.formats[0] is not None
    # Provenance lets the UI show model vs derived values.
    assert any(entry.source == "model" for entry in result.provenance)
    assert any(entry.source == "derived" for entry in result.provenance)


async def test_generation_record_captures_audit_fields(tmp_path: Path) -> None:
    store = FileProjectStore(tmp_path)
    project_id, revision = _new_project(store)
    service = _service(ScriptedLLMProvider([model_result(CANNED_BLUEPRINT)]), store)

    await service.generate(
        CharacterGenerationInput(
            project_id=project_id, expected_revision=revision, model="planner", description="x"
        )
    )

    record = store.get_project(project_id).document.generation_records[0]
    assert record.model_name
    assert record.prompt_ids == (
        "character_blueprint.system.v1",
        "character_blueprint.user.v1",
    )
    assert record.options.temperature >= 0.0
    assert record.status == "succeeded"
    assert record.timing is not None
    assert record.blueprint is not None
    assert len(record.attempts) == 1


async def test_invalid_then_valid_triggers_repair(tmp_path: Path) -> None:
    store = FileProjectStore(tmp_path)
    project_id, revision = _new_project(store)
    provider = ScriptedLLMProvider(
        [content_result("this is not json"), model_result(CANNED_BLUEPRINT)]
    )
    service = _service(provider, store)

    result = await service.generate(
        CharacterGenerationInput(
            project_id=project_id, expected_revision=revision, model="planner", description="x"
        )
    )

    assert result.status == "repaired"
    record = store.get_project(project_id).document.generation_records[0]
    assert record.status == "repaired"
    assert [attempt.kind for attempt in record.attempts] == ["initial", "repair"]
    assert record.prompt_ids[-1] == "repair_json.system.v1"


async def test_still_invalid_fails_without_corrupting_project(tmp_path: Path) -> None:
    store = FileProjectStore(tmp_path)
    project_id, revision = _new_project(store)
    provider = ScriptedLLMProvider([content_result("bad one"), content_result("bad two")])
    service = _service(provider, store)

    with pytest.raises(GenerationInvalidResponse) as exc_info:
        await service.generate(
            CharacterGenerationInput(
                project_id=project_id, expected_revision=revision, model="planner", description="x"
            )
        )

    assert exc_info.value.kind == "invalid_response"
    assert exc_info.value.retryable is False
    assert exc_info.value.detail is not None
    # Project is untouched: no character, no record, same revision.
    stored = store.get_project(project_id)
    assert stored.document.characters == ()
    assert stored.document.generation_records == ()
    assert stored.revision == revision


async def test_timeout_is_retryable(tmp_path: Path) -> None:
    store = FileProjectStore(tmp_path)
    project_id, revision = _new_project(store)
    provider = ScriptedLLMProvider([ProviderTimeoutError("slow")])
    service = _service(provider, store)

    with pytest.raises(GenerationTimeout) as exc_info:
        await service.generate(
            CharacterGenerationInput(
                project_id=project_id, expected_revision=revision, model="planner", description="x"
            )
        )
    assert exc_info.value.kind == "timeout"
    assert exc_info.value.retryable is True


async def test_stale_revision_conflicts_and_saves_nothing(tmp_path: Path) -> None:
    store = FileProjectStore(tmp_path)
    project_id, _ = _new_project(store)
    provider = ScriptedLLMProvider([model_result(CANNED_BLUEPRINT)])
    service = _service(provider, store)

    with pytest.raises(GenerationConflict):
        await service.generate(
            CharacterGenerationInput(
                project_id=project_id,
                expected_revision="rev_stale",
                model="planner",
                description="x",
            )
        )
    assert store.get_project(project_id).document.characters == ()


async def test_sexual_prompt_is_refused_before_calling_model(tmp_path: Path) -> None:
    store = FileProjectStore(tmp_path)
    project_id, revision = _new_project(store)
    provider = ScriptedLLMProvider([model_result(CANNED_BLUEPRINT)])
    service = _service(provider, store)

    with pytest.raises(GenerationSafetyRefusal):
        await service.generate(
            CharacterGenerationInput(
                project_id=project_id,
                expected_revision=revision,
                model="planner",
                description="an explicit nude character",
            )
        )
    # The model was never called.
    assert provider.calls == []
