"""Provider-neutral contract for optional local image generation."""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import Field

from app.domain.common import DomainModel

type ImageRegion = Literal["hair", "face", "clothing", "full_character"]


class ImageGenerationProvenance(DomainModel):
    provider_name: str
    model_name: str
    prompt_version: str
    seed: int | None = None
    segmentation_required: bool = True
    local_only: bool = True


class ImageGenerationRequest(DomainModel):
    region: ImageRegion
    prompt: str = Field(min_length=1, max_length=4000)
    negative_prompt: str = Field(default="", max_length=4000)
    width: int = Field(default=1024, ge=64, le=4096)
    height: int = Field(default=1024, ge=64, le=4096)
    transparent_background: bool = True
    provenance: ImageGenerationProvenance


class ImageGenerationResult(DomainModel):
    asset_id: str = Field(pattern=r"^asset_[a-z0-9][a-z0-9_-]*$")
    media_type: Literal["image/png", "image/webp"]
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    provenance: ImageGenerationProvenance
    segmentation_mask_asset_id: str | None = Field(
        default=None, pattern=r"^asset_[a-z0-9][a-z0-9_-]*$"
    )
    warnings: tuple[str, ...] = ()


class ImageGenerationProvider(Protocol):
    """Optional adapter boundary for local diffusion/ComfyUI style providers."""

    async def health(self) -> bool: ...

    async def generate_image(
        self,
        request: ImageGenerationRequest,
        *,
        request_id: str,
    ) -> ImageGenerationResult: ...
