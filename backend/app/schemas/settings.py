from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SettingsRead(BaseModel):
    app_name: str
    app_version: str
    environment: str
    api_base_path: str
    asset_store_path: str
    ollama_base_url: str
    ollama_generation_timeout_seconds: float
    ollama_keep_alive: str

    model_config = ConfigDict(frozen=True)
