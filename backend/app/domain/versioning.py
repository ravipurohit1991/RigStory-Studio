"""Semantic schema and engine versions."""

from __future__ import annotations

import re
from dataclasses import dataclass

_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")

PROJECT_FORMAT = "rigstory-project"


@dataclass(frozen=True, order=True, slots=True)
class SchemaVersion:
    major: int
    minor: int
    patch: int

    @staticmethod
    def parse(value: str) -> SchemaVersion:
        match = _SEMVER_RE.fullmatch(value)
        if match is None:
            raise ValueError(f"invalid semantic version: {value!r}")
        major, minor, patch = (int(part) for part in match.groups())
        return SchemaVersion(major, minor, patch)

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


# The current version of the persisted project document schema.
# 0.4.0 introduced explicit scene object visuals, edit flags, collision masks,
# and walkable/blocked summaries.
# 0.5.0 replaced the reserved empty ``motion_plans`` placeholder with the real
# MotionPlan schema and linked compiled clips to their source plan.
# 0.6.0 added weighted mesh attachment payloads while preserving rigid
# attachment documents unchanged.
PROJECT_SCHEMA_VERSION = SchemaVersion(0, 6, 0)

# The version of the deterministic engine that produced or evaluated data.
ENGINE_VERSION = SchemaVersion(0, 1, 0)
