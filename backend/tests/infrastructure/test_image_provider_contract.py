from __future__ import annotations

from app.infrastructure.image_generation.provider import (
    ImageGenerationProvenance,
    ImageGenerationRequest,
    ImageGenerationResult,
)


def test_optional_image_generation_contract_records_provenance() -> None:
    provenance = ImageGenerationProvenance(
        provider_name="comfyui-local",
        model_name="example-model",
        prompt_version="image_region.v1",
        seed=42,
    )
    request = ImageGenerationRequest(
        region="clothing",
        prompt="transparent jacket panel",
        provenance=provenance,
    )
    result = ImageGenerationResult(
        asset_id="asset_jacket_panel",
        media_type="image/png",
        width=request.width,
        height=request.height,
        provenance=provenance,
        segmentation_mask_asset_id="asset_jacket_mask",
    )

    assert request.provenance.local_only is True
    assert request.provenance.segmentation_required is True
    assert result.provenance == provenance
    assert result.segmentation_mask_asset_id == "asset_jacket_mask"
