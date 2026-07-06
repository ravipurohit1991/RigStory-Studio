from __future__ import annotations

import pytest

from app.domain.blueprint import (
    CANNED_BLUEPRINT,
    BlueprintAppearance,
    CharacterBlueprint,
    ClothingItem,
    FaceSpec,
    HairSpec,
    SkinPalette,
    blueprint_to_builder_request,
    scan_prompt_safety,
    validate_character_blueprint,
)


def test_canned_blueprint_is_valid_and_safe() -> None:
    assert validate_character_blueprint(CANNED_BLUEPRINT) == []


def test_mapping_uses_model_clothing_and_colors() -> None:
    mapping = blueprint_to_builder_request(CANNED_BLUEPRINT)
    request = mapping.request
    assert request.top == "shirt"
    assert request.bottom == "trousers"
    assert request.footwear == "shoes"
    assert request.hair_style == "bob"
    assert request.palette.skin == "#8b5a3c"
    assert request.palette.hair == "#241a17"
    assert request.palette.top == "#315b7d"


def test_mapping_is_deterministic() -> None:
    first = blueprint_to_builder_request(CANNED_BLUEPRINT)
    second = blueprint_to_builder_request(CANNED_BLUEPRINT)
    assert first.model_dump() == second.model_dump()


def test_provenance_distinguishes_model_derived_and_default() -> None:
    # A blueprint with no clothing so slots fall back to defaults.
    bare = CANNED_BLUEPRINT.model_copy(update={"clothing": ()})
    mapping = blueprint_to_builder_request(bare)
    by_field = {entry.field: entry.source for entry in mapping.provenance}
    assert by_field["name"] == "model"
    assert by_field["palette.skin"] == "model"
    assert by_field["proportions.shoulder_width"] == "derived"
    assert by_field["height"] == "derived"
    assert by_field["top"] == "default"
    assert by_field["palette.top"] == "default"


def test_duplicate_top_garment_warns_and_last_wins() -> None:
    blueprint = CANNED_BLUEPRINT.model_copy(
        update={
            "clothing": (
                ClothingItem(id="a", slot="top", category="shirt", primary_color="#111111"),
                ClothingItem(id="b", slot="top", category="jacket", primary_color="#222222"),
            )
        }
    )
    mapping = blueprint_to_builder_request(blueprint)
    assert mapping.request.top == "jacket"
    assert mapping.request.palette.top == "#222222"
    assert any("multiple top garments" in warning for warning in mapping.warnings)


def test_clothing_slot_mismatch_is_flagged() -> None:
    blueprint = CANNED_BLUEPRINT.model_copy(
        update={
            "clothing": (
                ClothingItem(id="wrong", slot="bottom", category="shirt", primary_color="#111111"),
            )
        }
    )
    codes = {issue.code for issue in validate_character_blueprint(blueprint)}
    assert "BLUEPRINT_CLOTHING_SLOT_MISMATCH" in codes


def test_duplicate_clothing_id_is_flagged() -> None:
    blueprint = CANNED_BLUEPRINT.model_copy(
        update={
            "clothing": (
                ClothingItem(id="dup", slot="top", category="shirt", primary_color="#111111"),
                ClothingItem(id="dup", slot="bottom", category="trousers", primary_color="#222222"),
            )
        }
    )
    codes = {issue.code for issue in validate_character_blueprint(blueprint)}
    assert "BLUEPRINT_DUPLICATE_CLOTHING_ID" in codes


def test_sexualized_minor_content_is_rejected() -> None:
    blueprint = CANNED_BLUEPRINT.model_copy(
        update={"age_category": "child", "character_name": "revealing kid"}
    )
    codes = {issue.code for issue in validate_character_blueprint(blueprint)}
    assert "BLUEPRINT_UNSAFE_MINOR_CONTENT" in codes


def test_sexualized_adult_content_is_rejected() -> None:
    blueprint = CANNED_BLUEPRINT.model_copy(
        update={
            "clothing": (
                ClothingItem(
                    id="x",
                    slot="top",
                    category="shirt",
                    silhouette="lingerie",
                    primary_color="#111111",
                ),
            )
        }
    )
    codes = {issue.code for issue in validate_character_blueprint(blueprint)}
    assert "BLUEPRINT_UNSAFE_CONTENT" in codes


def test_head_units_drive_height_class() -> None:
    tall = CANNED_BLUEPRINT.model_copy(
        update={
            "proportions": CANNED_BLUEPRINT.proportions.model_copy(update={"head_units_tall": 8.2})
        }
    )
    short = CANNED_BLUEPRINT.model_copy(
        update={
            "proportions": CANNED_BLUEPRINT.proportions.model_copy(update={"head_units_tall": 6.2})
        }
    )
    assert blueprint_to_builder_request(tall).request.height == "tall"
    assert blueprint_to_builder_request(short).request.height == "short"


def test_scan_prompt_safety_hard_terms_only() -> None:
    assert scan_prompt_safety("a cheerful nurse") is None
    # "revealing" is a soft term and is intentionally not flagged in raw prompts.
    assert scan_prompt_safety("revealing a secret plan") is None
    assert scan_prompt_safety("an explicit nude figure") == "nude"


def test_schema_is_usable_as_structured_output_format() -> None:
    schema = CharacterBlueprint.model_json_schema()
    assert "character_name" in schema["required"]
    assert schema["additionalProperties"] is False


@pytest.mark.parametrize("bad_color", ["red", "#12", "#1234567", "3a2a20"])
def test_invalid_hex_colors_rejected(bad_color: str) -> None:
    with pytest.raises(ValueError):
        BlueprintAppearance(
            skin_palette=SkinPalette(base=bad_color),
            hair=HairSpec(),
            face=FaceSpec(),
        )
