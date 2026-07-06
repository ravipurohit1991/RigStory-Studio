from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

type MediaExportFormat = Literal["animated_svg", "png_sequence", "webm"]


class MediaExportRequest(BaseModel):
    format: MediaExportFormat = "png_sequence"
    frame_rate: int = Field(default=24, ge=1, le=120)
    width: int = Field(default=1280, ge=16, le=4096)
    height: int = Field(default=720, ge=16, le=4096)
    background: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    transparent: bool = True

    model_config = ConfigDict(frozen=True)


class MediaExportRead(BaseModel):
    export_id: str
    clip_id: str
    format: MediaExportFormat
    file_name: str
    media_type: str
    download_url: str
    byte_length: int
    sha256: str
    duration: float
    frame_rate: int
    frame_count: int
    width: int
    height: int

    model_config = ConfigDict(frozen=True)
