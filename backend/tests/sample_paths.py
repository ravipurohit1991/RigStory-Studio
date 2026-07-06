"""Paths and loaders for the shared fixtures under ``samples/``."""

from __future__ import annotations

import json
from pathlib import Path

from app.domain.canonical import JsonValue

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLES_DIR = REPO_ROOT / "samples"


def load_sample(relative_path: str) -> dict[str, JsonValue]:
    path = SAMPLES_DIR / relative_path
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict), f"{relative_path} must contain a JSON object"
    return raw
