"""Shared schema building blocks for domain documents.

Validation is split in two layers:

- Intra-object shape (types, ranges, enums) lives in Pydantic models and
  rejects malformed data at parse time.
- Cross-object invariants (hierarchy cycles, reference integrity) live in
  ``validate_*`` functions that return coded ``ValidationIssue`` lists, so
  callers can report every problem at once.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator

from app.domain.math2d.transform import Transform2D
from app.domain.math2d.vec2 import Vec2


class DomainModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# Serialized as JSON arrays: [x, y] and [min_x, min_y, max_x, max_y].
type Point2 = tuple[float, float]
type Scale2 = tuple[float, float]
type Bounds4 = tuple[float, float, float, float]


class TransformSpec(DomainModel):
    """Serialized TRS transform, local to its parent. Y-up, CCW degrees."""

    position: Point2 = (0.0, 0.0)
    rotation_deg: float = 0.0
    scale: Scale2 = (1.0, 1.0)

    @model_validator(mode="after")
    def _check_scale(self) -> TransformSpec:
        if self.scale[0] == 0.0 or self.scale[1] == 0.0:
            raise ValueError("scale components must be non-zero")
        return self

    def to_transform2d(self) -> Transform2D:
        return Transform2D(
            position=Vec2(self.position[0], self.position[1]),
            rotation_deg=self.rotation_deg,
            scale=self.scale,
        )


IDENTITY_TRANSFORM = TransformSpec()


def bounds_are_valid(bounds: Bounds4) -> bool:
    min_x, min_y, max_x, max_y = bounds
    return min_x <= max_x and min_y <= max_y
