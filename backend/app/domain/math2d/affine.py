"""2D affine matrix.

Represents the 3x3 matrix::

    | a  c  tx |
    | b  d  ty |
    | 0  0  1  |

Columns (a, b) and (c, d) are the images of the X and Y basis vectors.
Affine matrices are closed under composition, unlike TRS transforms with
non-uniform scale, so world transforms are always composed as matrices.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.domain.math2d.vec2 import Vec2


@dataclass(frozen=True, slots=True)
class Affine2:
    a: float
    b: float
    c: float
    d: float
    tx: float
    ty: float

    @staticmethod
    def identity() -> Affine2:
        return Affine2(1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

    @staticmethod
    def from_trs(
        translation: Vec2,
        rotation_deg: float,
        scale: tuple[float, float] = (1.0, 1.0),
    ) -> Affine2:
        radians = math.radians(rotation_deg)
        cos_r = math.cos(radians)
        sin_r = math.sin(radians)
        sx, sy = scale
        return Affine2(
            a=cos_r * sx,
            b=sin_r * sx,
            c=-sin_r * sy,
            d=cos_r * sy,
            tx=translation.x,
            ty=translation.y,
        )

    def multiply(self, other: Affine2) -> Affine2:
        """Return ``self @ other`` (apply ``other`` first, then ``self``)."""
        return Affine2(
            a=self.a * other.a + self.c * other.b,
            b=self.b * other.a + self.d * other.b,
            c=self.a * other.c + self.c * other.d,
            d=self.b * other.c + self.d * other.d,
            tx=self.a * other.tx + self.c * other.ty + self.tx,
            ty=self.b * other.tx + self.d * other.ty + self.ty,
        )

    def determinant(self) -> float:
        return self.a * self.d - self.b * self.c

    def inverse(self) -> Affine2:
        det = self.determinant()
        if abs(det) <= 1e-12:
            raise ValueError("matrix is singular and cannot be inverted")
        inv_det = 1.0 / det
        a = self.d * inv_det
        b = -self.b * inv_det
        c = -self.c * inv_det
        d = self.a * inv_det
        return Affine2(
            a=a,
            b=b,
            c=c,
            d=d,
            tx=-(a * self.tx + c * self.ty),
            ty=-(b * self.tx + d * self.ty),
        )

    def apply_point(self, point: Vec2) -> Vec2:
        return Vec2(
            self.a * point.x + self.c * point.y + self.tx,
            self.b * point.x + self.d * point.y + self.ty,
        )

    def apply_vector(self, vector: Vec2) -> Vec2:
        """Transform a direction: rotation and scale apply, translation does not."""
        return Vec2(
            self.a * vector.x + self.c * vector.y,
            self.b * vector.x + self.d * vector.y,
        )

    def translation(self) -> Vec2:
        return Vec2(self.tx, self.ty)

    def rotation_deg(self) -> float:
        """Rotation of the X basis vector in degrees."""
        return math.degrees(math.atan2(self.b, self.a))

    def is_close(self, other: Affine2, tolerance: float = 1e-9) -> bool:
        return (
            abs(self.a - other.a) <= tolerance
            and abs(self.b - other.b) <= tolerance
            and abs(self.c - other.c) <= tolerance
            and abs(self.d - other.d) <= tolerance
            and abs(self.tx - other.tx) <= tolerance
            and abs(self.ty - other.ty) <= tolerance
        )
