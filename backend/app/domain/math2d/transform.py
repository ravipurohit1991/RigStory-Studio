"""TRS transform matching the serialized JSON convention.

A transform is serialized as::

    {"position": [x, y], "rotation_deg": deg, "scale": [sx, sy]}

Every transform is local to its parent. World transforms are computed by
composing parent matrices from root to leaf; composition happens in matrix
form because TRS is not closed under composition with non-uniform scale.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.math2d.affine import Affine2
from app.domain.math2d.vec2 import Vec2


@dataclass(frozen=True, slots=True)
class Transform2D:
    position: Vec2 = field(default_factory=Vec2.zero)
    rotation_deg: float = 0.0
    scale: tuple[float, float] = (1.0, 1.0)

    @staticmethod
    def identity() -> Transform2D:
        return Transform2D()

    def to_affine(self) -> Affine2:
        return Affine2.from_trs(self.position, self.rotation_deg, self.scale)

    def compose_affine(self, parent_world: Affine2) -> Affine2:
        """World matrix of this local transform under ``parent_world``."""
        return parent_world.multiply(self.to_affine())
