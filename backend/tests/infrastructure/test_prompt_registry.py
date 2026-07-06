from __future__ import annotations

import pytest

from app.infrastructure.llm.prompt_registry import (
    CHARACTER_BLUEPRINT_SYSTEM,
    CHARACTER_BLUEPRINT_USER,
    REPAIR_JSON_SYSTEM,
    PromptNotFoundError,
    PromptRegistry,
)


def test_all_declared_prompts_load() -> None:
    registry = PromptRegistry()
    for prompt_id in (
        CHARACTER_BLUEPRINT_SYSTEM,
        CHARACTER_BLUEPRINT_USER,
        REPAIR_JSON_SYSTEM,
    ):
        assert registry.get(prompt_id).text.strip()


def test_system_prompt_contains_required_safeguards() -> None:
    text = PromptRegistry().get(CHARACTER_BLUEPRINT_SYSTEM).text
    # Field preservation (specs §22.1).
    assert "Preserve every attribute" in text
    # Bias/stereotype safeguard.
    assert "stereotype" in text.lower()
    # Child/teen safety restriction (specs §30).
    assert "child" in text and "teen" in text
    # No raw art or code.
    assert "SVG" in text
    # Never invent fields.
    assert "invent fields" in text


def test_user_prompt_renders_placeholders() -> None:
    rendered = PromptRegistry().render(
        CHARACTER_BLUEPRINT_USER,
        description="a tall calm woman",
        form_summary="- age_category: adult",
        schema='{"type": "object"}',
    )
    assert "a tall calm woman" in rendered
    assert "- age_category: adult" in rendered
    assert '{"type": "object"}' in rendered
    assert "{{" not in rendered


def test_missing_placeholder_value_is_an_error() -> None:
    with pytest.raises(KeyError):
        PromptRegistry().render(CHARACTER_BLUEPRINT_USER, description="only one value")


def test_unknown_prompt_raises() -> None:
    with pytest.raises(PromptNotFoundError):
        PromptRegistry().get("does.not.exist.v1")
