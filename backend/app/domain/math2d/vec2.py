"""Immutable 2D vector."""

from __future__ import annotations

import math
from dataclasses import dataclass

DEFAULT_TOLERANCE = 1e-9


@dataclass(frozen=True, slots=True)
class Vec2:
    x: float
    y: float

    @staticmethod
    def zero() -> Vec2:
        return Vec2(0.0, 0.0)

    def __add__(self, other: Vec2) -> Vec2:
        return Vec2(self.x + other.x, self.y + other.y)

    def __sub__(self, other: Vec2) -> Vec2:
        return Vec2(self.x - other.x, self.y - other.y)

    def __neg__(self) -> Vec2:
        return Vec2(-self.x, -self.y)

    def scaled(self, factor: float) -> Vec2:
        return Vec2(self.x * factor, self.y * factor)

    def dot(self, other: Vec2) -> float:
        return self.x * other.x + self.y * other.y

    def cross(self, other: Vec2) -> float:
        """Z component of the 3D cross product; positive when ``other`` is CCW."""
        return self.x * other.y - self.y * other.x

    def length_squared(self) -> float:
        return self.x * self.x + self.y * self.y

    def length(self) -> float:
        return math.hypot(self.x, self.y)

    def distance_to(self, other: Vec2) -> float:
        return math.hypot(self.x - other.x, self.y - other.y)

    def normalized(self) -> Vec2:
        magnitude = self.length()
        if magnitude <= DEFAULT_TOLERANCE:
            raise ValueError("cannot normalize a zero-length vector")
        return Vec2(self.x / magnitude, self.y / magnitude)

    def perpendicular(self) -> Vec2:
        """Rotate 90 degrees counterclockwise."""
        return Vec2(-self.y, self.x)

    def lerp(self, other: Vec2, t: float) -> Vec2:
        return Vec2(self.x + (other.x - self.x) * t, self.y + (other.y - self.y) * t)

    def angle_deg(self) -> float:
        """Counterclockwise angle from the +X axis in degrees."""
        return math.degrees(math.atan2(self.y, self.x))

    def rotated_deg(self, degrees: float) -> Vec2:
        radians = math.radians(degrees)
        cos_r = math.cos(radians)
        sin_r = math.sin(radians)
        return Vec2(self.x * cos_r - self.y * sin_r, self.x * sin_r + self.y * cos_r)

    def is_close(self, other: Vec2, tolerance: float = 1e-6) -> bool:
        return abs(self.x - other.x) <= tolerance and abs(self.y - other.y) <= tolerance
