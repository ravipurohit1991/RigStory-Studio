"""Versioned prompt registry (specs §21.4).

Prompts are versioned Markdown files on disk, not inline strings scattered
through services, so a job can record exactly which prompt version produced it.
Templates use ``{{token}}`` placeholders; ``{`` and ``}`` are otherwise literal,
which matters because rendered prompts embed JSON schemas.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

_TOKEN = re.compile(r"\{\{(\w+)\}\}")

CHARACTER_BLUEPRINT_SYSTEM = "character_blueprint.system.v1"
CHARACTER_BLUEPRINT_USER = "character_blueprint.user.v1"
MOTION_PLAN_SYSTEM = "motion_plan.system.v1"
MOTION_PLAN_USER = "motion_plan.user.v1"
PLAN_PATCH_SYSTEM = "plan_patch.system.v1"
PLAN_PATCH_USER = "plan_patch.user.v1"
REPAIR_JSON_SYSTEM = "repair_json.system.v1"


class PromptNotFoundError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    id: str
    text: str

    def render(self, **values: str) -> str:
        def replace(match: re.Match[str]) -> str:
            key = match.group(1)
            if key not in values:
                raise KeyError(f"prompt {self.id!r} is missing value for {key!r}")
            return values[key]

        return _TOKEN.sub(replace, self.text)


class PromptRegistry:
    def __init__(self, base_dir: Path = PROMPTS_DIR) -> None:
        self._base_dir = base_dir
        self._cache: dict[str, PromptTemplate] = {}

    def get(self, prompt_id: str) -> PromptTemplate:
        cached = self._cache.get(prompt_id)
        if cached is not None:
            return cached
        path = self._base_dir / f"{prompt_id}.md"
        if not path.exists():
            raise PromptNotFoundError(prompt_id)
        template = PromptTemplate(id=prompt_id, text=path.read_text(encoding="utf-8"))
        self._cache[prompt_id] = template
        return template

    def render(self, prompt_id: str, **values: str) -> str:
        return self.get(prompt_id).render(**values)
