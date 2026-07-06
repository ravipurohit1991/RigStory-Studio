"""``CharacterBlueprint``: the validated LLM output for character generation.

The blueprint describes *intent* and proportions, never raw SVG or executable
code (specs §12). A local model returns a blueprint; the deterministic
builder — not the model — turns it into an editable rig and vector art.

Two pure, deterministic operations live here:

- ``validate_character_blueprint`` checks coherence and safety restrictions and
  returns coded :class:`ValidationIssue` values (specs §12.2, §30).
- ``blueprint_to_builder_request`` maps a blueprint onto the existing
  :class:`CharacterBuilderRequest`, recording per-field provenance so the UI can
  show which values came from the model and which were derived or defaulted
  acceptance criterion).
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.domain.character_builder import (
    CharacterBuilderRequest,
    CharacterPalette,
    CharacterProportions,
)
from app.domain.common import DomainModel
from app.domain.errors import ValidationIssue

BLUEPRINT_SCHEMA_VERSION = "1.0"

HEX_COLOR = r"^#[0-9a-fA-F]{6}$"
SAFE_NAME = r"^[\w][\w '\-.]{0,58}[\w.]$|^[\w]$"
SLUG_OR_EMPTY = r"^$|^[a-z][a-z0-9_]*$"

type StyleFamily = Literal[
    "flat_vector",
    "cartoon",
    "graphic_novel",
    "paper_cutout",
    "silhouette",
]
type DetailLevel = Literal["low", "medium", "high"]
type BlueprintPresentation = Literal["masculine", "feminine", "neutral"]
type BlueprintAgeCategory = Literal["child", "teen", "adult", "older_adult"]
type BlueprintBuild = Literal["slender", "average", "sturdy", "broad"]
type BlueprintHairStyle = Literal["bald", "short", "bob", "curly", "long", "coily"]
type BlueprintFaceShape = Literal["round", "oval", "square", "heart", "long"]
type JointFlexibility = Literal["reduced", "normal", "high"]

type ClothingSlot = Literal["top", "bottom", "footwear", "outerwear"]
type BlueprintRegion = Literal["hair", "face", "clothing"]
type TopCategory = Literal["tshirt", "shirt", "sweater", "jacket"]
type BottomCategory = Literal["trousers", "shorts", "skirt"]
type FootwearCategory = Literal["shoes", "boots", "sneakers"]
type OuterwearCategory = Literal["vest", "coat"]
type ClothingCategory = Literal[
    "tshirt",
    "shirt",
    "sweater",
    "jacket",
    "trousers",
    "shorts",
    "skirt",
    "shoes",
    "boots",
    "sneakers",
    "vest",
    "coat",
]

_CATEGORY_SLOTS: dict[str, ClothingSlot] = {
    "tshirt": "top",
    "shirt": "top",
    "sweater": "top",
    "jacket": "top",
    "trousers": "bottom",
    "shorts": "bottom",
    "skirt": "bottom",
    "shoes": "footwear",
    "boots": "footwear",
    "sneakers": "footwear",
    "vest": "outerwear",
    "coat": "outerwear",
}

# Terms that indicate sexualized intent. Scanned in blueprint free-text fields
# and, upstream, in the user prompt. Kept deliberately clinical.
_UNSAFE_TERMS: frozenset[str] = frozenset(
    {
        "nude",
        "naked",
        "topless",
        "lingerie",
        "underwear",
        "bikini",
        "sexual",
        "sexualized",
        "sexualised",
        "erotic",
        "fetish",
        "seductive",
        "provocative",
        "revealing",
        "nsfw",
    }
)

# The subset scanned in raw user prompts, where softer terms would false-positive
# (for example "revealing a secret"). Blueprint fields use the full list above.
_HARD_UNSAFE_TERMS: frozenset[str] = frozenset(
    {
        "nude",
        "naked",
        "topless",
        "lingerie",
        "bikini",
        "sexual",
        "sexualized",
        "sexualised",
        "erotic",
        "fetish",
        "nsfw",
    }
)

# Proportion baselines used to convert head-relative measures into the builder's
# normalized multipliers (a baseline maps to a multiplier of 1.0).
HEAD_UNITS_BASE = 7.25
SHOULDER_HEADS_BASE = 2.3
HIP_HEADS_BASE = 1.6
TORSO_HEADS_BASE = 2.1
ARM_HEADS_BASE = 3.0
LEG_HEADS_BASE = 3.8


class BlueprintStyle(DomainModel):
    family: StyleFamily = "flat_vector"
    outline_weight: float = Field(default=2.0, ge=0.0, le=8.0)
    detail_level: DetailLevel = "medium"
    symmetry: float = Field(default=0.9, ge=0.0, le=1.0)


class BlueprintProportions(DomainModel):
    head_units_tall: float = Field(default=7.25, ge=3.0, le=9.0)
    shoulder_width_heads: float = Field(default=2.3, ge=1.0, le=3.5)
    hip_width_heads: float = Field(default=1.6, ge=0.8, le=2.8)
    torso_length_heads: float = Field(default=2.1, ge=1.2, le=3.0)
    arm_length_heads: float = Field(default=3.0, ge=1.8, le=4.2)
    leg_length_heads: float = Field(default=3.8, ge=2.2, le=5.0)
    build: BlueprintBuild = "average"


class SkinPalette(DomainModel):
    base: str = Field(default="#c98f62", pattern=HEX_COLOR)
    shadow: str = Field(default="#8a5f40", pattern=HEX_COLOR)
    highlight: str = Field(default="#e3b085", pattern=HEX_COLOR)


class HairSpec(DomainModel):
    style: BlueprintHairStyle = "short"
    color: str = Field(default="#3d2a1e", pattern=HEX_COLOR)


class FaceSpec(DomainModel):
    shape: BlueprintFaceShape = "oval"
    eye_shape: str = Field(default="almond", pattern=SLUG_OR_EMPTY)
    eye_color: str = Field(default="#3a2a20", pattern=HEX_COLOR)
    nose_style: str = Field(default="simple", pattern=SLUG_OR_EMPTY)
    mouth_style: str = Field(default="soft", pattern=SLUG_OR_EMPTY)


class BlueprintAppearance(DomainModel):
    skin_palette: SkinPalette = SkinPalette()
    hair: HairSpec = HairSpec()
    face: FaceSpec = FaceSpec()


class ClothingItem(DomainModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    slot: ClothingSlot
    category: ClothingCategory
    silhouette: str = Field(default="", pattern=SLUG_OR_EMPTY, max_length=40)
    primary_color: str = Field(default="#2f6f73", pattern=HEX_COLOR)
    secondary_color: str | None = Field(default=None, pattern=HEX_COLOR)
    layer: str = Field(default="", pattern=SLUG_OR_EMPTY, max_length=40)


class RigProfile(DomainModel):
    template: Literal["human_biped_v1"] = "human_biped_v1"
    allow_exaggeration: bool = True
    joint_flexibility: JointFlexibility = "normal"


class CharacterBlueprint(DomainModel):
    """Primary LLM output for character generation (specs §12)."""

    schema_version: Literal["1.0"] = "1.0"
    character_name: str = Field(pattern=SAFE_NAME)
    presentation: BlueprintPresentation
    age_category: BlueprintAgeCategory
    style: BlueprintStyle = BlueprintStyle()
    proportions: BlueprintProportions = BlueprintProportions()
    appearance: BlueprintAppearance = BlueprintAppearance()
    clothing: tuple[ClothingItem, ...] = ()
    rig_profile: RigProfile = RigProfile()
    warnings: tuple[str, ...] = ()


class FieldProvenance(DomainModel):
    """How one builder-request field was obtained from a blueprint."""

    field: str
    source: Literal["model", "derived", "default"]
    model_value: str | float | bool | None = None


class BlueprintMappingResult(DomainModel):
    request: CharacterBuilderRequest
    provenance: tuple[FieldProvenance, ...]
    warnings: tuple[str, ...] = ()


def _contains_unsafe_term(text: str) -> str | None:
    lowered = text.lower()
    for term in _UNSAFE_TERMS:
        if term in lowered:
            return term
    return None


def scan_prompt_safety(text: str) -> str | None:
    """Return the first clearly sexual term in a raw user prompt, or ``None``."""
    lowered = text.lower()
    for term in _HARD_UNSAFE_TERMS:
        if term in lowered:
            return term
    return None


def validate_character_blueprint(
    blueprint: CharacterBlueprint, path_prefix: str = ""
) -> list[ValidationIssue]:
    """Coherence and safety checks beyond the Pydantic shape (specs §12.2)."""
    prefix = f"{path_prefix}." if path_prefix else ""
    issues: list[ValidationIssue] = []

    if blueprint.schema_version != BLUEPRINT_SCHEMA_VERSION:
        issues.append(
            ValidationIssue(
                "BLUEPRINT_UNSUPPORTED_VERSION",
                f"blueprint schema_version {blueprint.schema_version!r} is not supported",
                f"{prefix}schema_version",
            )
        )

    seen_clothing: set[str] = set()
    for index, item in enumerate(blueprint.clothing):
        item_path = f"{prefix}clothing[{index}]"
        if item.id in seen_clothing:
            issues.append(
                ValidationIssue(
                    "BLUEPRINT_DUPLICATE_CLOTHING_ID",
                    f"clothing id {item.id!r} is defined more than once",
                    f"{item_path}.id",
                )
            )
        seen_clothing.add(item.id)
        if _CATEGORY_SLOTS[item.category] != item.slot:
            issues.append(
                ValidationIssue(
                    "BLUEPRINT_CLOTHING_SLOT_MISMATCH",
                    f"clothing {item.id!r} category {item.category!r} does not belong "
                    f"in slot {item.slot!r}",
                    f"{item_path}.slot",
                )
            )

    # Safety: no sexualized content, and stricter scanning for minors (specs §30).
    minor = blueprint.age_category in ("child", "teen")
    scan_targets: list[tuple[str, str]] = [(f"{prefix}character_name", blueprint.character_name)]
    for index, item in enumerate(blueprint.clothing):
        scan_targets.append((f"{prefix}clothing[{index}].silhouette", item.silhouette))
    for index, warning in enumerate(blueprint.warnings):
        scan_targets.append((f"{prefix}warnings[{index}]", warning))
    for field_path, value in scan_targets:
        term = _contains_unsafe_term(value)
        if term is not None:
            code = "BLUEPRINT_UNSAFE_MINOR_CONTENT" if minor else "BLUEPRINT_UNSAFE_CONTENT"
            issues.append(
                ValidationIssue(
                    code,
                    f"sexualized term {term!r} is not permitted"
                    + (" for child/teen characters" if minor else ""),
                    field_path,
                )
            )

    return issues


def _height_class_from_head_units(head_units_tall: float) -> Literal["short", "average", "tall"]:
    if head_units_tall < 6.9:
        return "short"
    if head_units_tall > 7.7:
        return "tall"
    return "average"


def _waist_width_for_build(build: BlueprintBuild) -> float:
    return {"slender": 0.9, "average": 1.0, "sturdy": 1.08, "broad": 1.14}[build]


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(max(value, minimum), maximum)


def blueprint_to_builder_request(blueprint: CharacterBlueprint) -> BlueprintMappingResult:
    """Deterministically map a blueprint onto a builder request with provenance.

    The builder performs its own numeric normalization and records every clamp
    as a diagnostic. Here we only translate blueprint intent; the recorded
    provenance captures the model/derived value *before* that normalization.
    """
    provenance: list[FieldProvenance] = []
    warnings: list[str] = []

    def model(field: str, value: str | float | bool) -> None:
        provenance.append(FieldProvenance(field=field, source="model", model_value=value))

    def derived(field: str, value: str | float | bool) -> None:
        provenance.append(FieldProvenance(field=field, source="derived", model_value=value))

    def default(field: str, value: str | float | bool) -> None:
        provenance.append(FieldProvenance(field=field, source="default", model_value=value))

    p = blueprint.proportions
    proportions = CharacterProportions(
        shoulder_width=_clamp(p.shoulder_width_heads / SHOULDER_HEADS_BASE, 0.75, 1.25),
        torso_length=_clamp(p.torso_length_heads / TORSO_HEADS_BASE, 0.82, 1.18),
        waist_width=_clamp(_waist_width_for_build(p.build), 0.72, 1.18),
        hip_width=_clamp(p.hip_width_heads / HIP_HEADS_BASE, 0.75, 1.25),
        arm_length=_clamp(p.arm_length_heads / ARM_HEADS_BASE, 0.84, 1.18),
        leg_length=_clamp(p.leg_length_heads / LEG_HEADS_BASE, 0.84, 1.2),
        head_size=_clamp(HEAD_UNITS_BASE / p.head_units_tall, 0.86, 1.16),
        asymmetry=_clamp((1.0 - blueprint.style.symmetry) * 0.1, 0.0, 0.04),
    )
    derived("proportions.shoulder_width", proportions.shoulder_width)
    derived("proportions.torso_length", proportions.torso_length)
    derived("proportions.waist_width", proportions.waist_width)
    derived("proportions.hip_width", proportions.hip_width)
    derived("proportions.arm_length", proportions.arm_length)
    derived("proportions.leg_length", proportions.leg_length)
    derived("proportions.head_size", proportions.head_size)
    derived("proportions.asymmetry", proportions.asymmetry)

    palette_defaults = CharacterPalette()
    palette_values: dict[str, str] = {
        "skin": blueprint.appearance.skin_palette.base,
        "hair": blueprint.appearance.hair.color,
        "top": palette_defaults.top,
        "bottom": palette_defaults.bottom,
        "shoes": palette_defaults.shoes,
        "accent": palette_defaults.accent,
    }
    model("palette.skin", palette_values["skin"])
    model("palette.hair", palette_values["hair"])

    # Resolve one garment per slot; later items win but warn about the shadowed one.
    slot_choices: dict[ClothingSlot, ClothingItem] = {}
    for item in blueprint.clothing:
        if item.slot in slot_choices:
            warnings.append(f"multiple {item.slot} garments supplied; using {item.category!r}")
        slot_choices[item.slot] = item

    builder_defaults = CharacterBuilderRequest()
    top = builder_defaults.top
    bottom = builder_defaults.bottom
    footwear = builder_defaults.footwear
    outerwear = builder_defaults.outerwear

    if "top" in slot_choices:
        chosen = slot_choices["top"]
        top = chosen.category  # type: ignore[assignment]
        palette_values["top"] = chosen.primary_color
        model("top", top)
        model("palette.top", palette_values["top"])
    else:
        default("top", top)
        default("palette.top", palette_values["top"])

    if "bottom" in slot_choices:
        chosen = slot_choices["bottom"]
        bottom = chosen.category  # type: ignore[assignment]
        palette_values["bottom"] = chosen.primary_color
        model("bottom", bottom)
        model("palette.bottom", palette_values["bottom"])
    else:
        default("bottom", bottom)
        default("palette.bottom", palette_values["bottom"])

    if "footwear" in slot_choices:
        chosen = slot_choices["footwear"]
        footwear = chosen.category  # type: ignore[assignment]
        palette_values["shoes"] = chosen.primary_color
        model("footwear", footwear)
        model("palette.shoes", palette_values["shoes"])
    else:
        default("footwear", footwear)
        default("palette.shoes", palette_values["shoes"])

    if "outerwear" in slot_choices:
        chosen = slot_choices["outerwear"]
        outerwear = chosen.category  # type: ignore[assignment]
        palette_values["accent"] = chosen.primary_color
        model("outerwear", outerwear)
        model("palette.accent", palette_values["accent"])
    else:
        default("outerwear", outerwear)
        default("palette.accent", palette_values["accent"])

    height = _height_class_from_head_units(p.head_units_tall)
    derived("height", height)
    model("name", blueprint.character_name)
    model("presentation", blueprint.presentation)
    model("age_category", blueprint.age_category)
    model("build", p.build)
    model("hair_style", blueprint.appearance.hair.style)
    model("face_shape", blueprint.appearance.face.shape)
    model("style", blueprint.style.family)

    request = CharacterBuilderRequest(
        name=blueprint.character_name,
        presentation=blueprint.presentation,
        age_category=blueprint.age_category,
        height=height,
        build=p.build,
        proportions=proportions,
        palette=CharacterPalette(
            skin=palette_values["skin"],
            hair=palette_values["hair"],
            top=palette_values["top"],
            bottom=palette_values["bottom"],
            shoes=palette_values["shoes"],
            accent=palette_values["accent"],
        ),
        hair_style=blueprint.appearance.hair.style,
        face_shape=blueprint.appearance.face.shape,
        top=top,
        bottom=bottom,
        footwear=footwear,
        outerwear=outerwear,
        style=blueprint.style.family,
    )

    return BlueprintMappingResult(
        request=request,
        provenance=tuple(provenance),
        warnings=tuple(warnings),
    )


def merge_regional_blueprint_update(
    base: CharacterBlueprint,
    update: CharacterBlueprint,
    region: BlueprintRegion,
) -> CharacterBlueprint:
    """Apply an AI-proposed regional blueprint while locking unrelated fields.

    The model may return a full ``CharacterBlueprint`` for schema simplicity,
    but only the requested region is allowed to change project intent. Rig,
    proportions, identity, presentation, age category, and unrelated appearance
    fields are preserved by construction.
    """
    if region == "hair":
        return base.model_copy(
            update={
                "appearance": base.appearance.model_copy(
                    update={"hair": update.appearance.hair}
                ),
                "warnings": (*base.warnings, *update.warnings),
            }
        )
    if region == "face":
        return base.model_copy(
            update={
                "appearance": base.appearance.model_copy(
                    update={"face": update.appearance.face}
                ),
                "warnings": (*base.warnings, *update.warnings),
            }
        )
    return base.model_copy(
        update={
            "clothing": update.clothing,
            "warnings": (*base.warnings, *update.warnings),
        }
    )


# A deterministic canned blueprint for tests and model-independent fallback
# (plan.md §10). It mirrors the specs §12.1 example.
CANNED_BLUEPRINT = CharacterBlueprint(
    character_name="Mira",
    presentation="feminine",
    age_category="adult",
    style=BlueprintStyle(
        family="flat_vector", outline_weight=2.0, detail_level="medium", symmetry=0.9
    ),
    proportions=BlueprintProportions(
        head_units_tall=7.25,
        shoulder_width_heads=2.35,
        hip_width_heads=1.65,
        torso_length_heads=2.15,
        arm_length_heads=3.05,
        leg_length_heads=3.85,
        build="slender",
    ),
    appearance=BlueprintAppearance(
        skin_palette=SkinPalette(base="#8b5a3c", shadow="#6e402c", highlight="#b97a55"),
        hair=HairSpec(style="bob", color="#241a17"),
        face=FaceSpec(shape="oval"),
    ),
    clothing=(
        ClothingItem(
            id="top",
            slot="top",
            category="shirt",
            silhouette="fitted_long_sleeve",
            primary_color="#315b7d",
            secondary_color="#e5d7c2",
            layer="torso_front",
        ),
        ClothingItem(
            id="bottom",
            slot="bottom",
            category="trousers",
            silhouette="straight",
            primary_color="#1f2630",
            layer="legs_front",
        ),
        ClothingItem(id="feet", slot="footwear", category="shoes", primary_color="#2b2b2b"),
    ),
    rig_profile=RigProfile(template="human_biped_v1", allow_exaggeration=True),
)
