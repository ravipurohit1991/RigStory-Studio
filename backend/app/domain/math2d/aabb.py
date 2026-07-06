"""Axis-aligned bounding box."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.domain.math2d.vec2 import Vec2


@dataclass(frozen=True, slots=True)
class Aabb:
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    def __post_init__(self) -> None:
        if self.min_x > self.max_x or self.min_y > self.max_y:
            raise ValueError(
                f"invalid AABB: min ({self.min_x}, {self.min_y}) "
                f"exceeds max ({self.max_x}, {self.max_y})"
            )

    @staticmethod
    def from_points(points: Iterable[Vec2]) -> Aabb:
        iterator = iter(points)
        try:
            first = next(iterator)
        except StopIteration:
            raise ValueError("cannot build an AABB from zero points") from None
        min_x = max_x = first.x
        min_y = max_y = first.y
        for point in iterator:
            min_x = min(min_x, point.x)
            min_y = min(min_y, point.y)
            max_x = max(max_x, point.x)
            max_y = max(max_y, point.y)
        return Aabb(min_x, min_y, max_x, max_y)

    def width(self) -> float:
        return self.max_x - self.min_x

    def height(self) -> float:
        return self.max_y - self.min_y

    def center(self) -> Vec2:
        return Vec2((self.min_x + self.max_x) / 2.0, (self.min_y + self.max_y) / 2.0)

    def contains_point(self, point: Vec2) -> bool:
        return self.min_x <= point.x <= self.max_x and self.min_y <= point.y <= self.max_y

    def intersects(self, other: Aabb) -> bool:
        return (
            self.min_x <= other.max_x
            and other.min_x <= self.max_x
            and self.min_y <= other.max_y
            and other.min_y <= self.max_y
        )

    def union(self, other: Aabb) -> Aabb:
        return Aabb(
            min(self.min_x, other.min_x),
            min(self.min_y, other.min_y),
            max(self.max_x, other.max_x),
            max(self.max_y, other.max_y),
        )

    def expanded(self, margin: float) -> Aabb:
        return Aabb(
            self.min_x - margin,
            self.min_y - margin,
            self.max_x + margin,
            self.max_y + margin,
        )
