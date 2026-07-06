from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "RigStory Studio"
    app_version: str = "0.1.0"
    environment: str = "local"
    api_v1_prefix: str = "/api/v1"
    frontend_origin: str = "http://localhost:5173"
    database_url: str = "postgresql+psycopg://rigstory:rigstory@localhost:5432/rigstory"
    asset_store_path: Path = Path("./data")
    ollama_base_url: str = "http://localhost:11434"
    # Short probe timeout for health and model listing.
    ollama_timeout_seconds: float = Field(default=1.5, gt=0)
    # Generation is slow; give it a much larger budget than the health probe.
    ollama_generation_timeout_seconds: float = Field(default=120.0, gt=0)
    ollama_keep_alive: str = "10m"
    ollama_temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    ollama_num_ctx: int | None = Field(default=None, ge=0)

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
