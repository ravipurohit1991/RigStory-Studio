"""Simple polygon helpers. Vertices are ordered; no self-intersection checks yet."""

from __future__ import annotations

from collections.abc import Sequence

from app.domain.math2d.vec2 import Vec2


def signed_area(vertices: Sequence[Vec2]) -> float:
    """Positive for counterclockwise winding (Y-up convention)."""
    if len(vertices) < 3:
        raise ValueError("a polygon requires at least three vertices")
    total = 0.0
    for index, current in enumerate(vertices):
        following = vertices[(index + 1) % len(vertices)]
        total += current.x * following.y - following.x * current.y
    return total / 2.0


def is_ccw(vertices: Sequence[Vec2]) -> bool:
    return signed_area(vertices) > 0.0


def centroid(vertices: Sequence[Vec2]) -> Vec2:
    area = signed_area(vertices)
    if abs(area) <= 1e-12:
        raise ValueError("cannot compute the centroid of a degenerate polygon")
    cx = 0.0
    cy = 0.0
    for index, current in enumerate(vertices):
        following = vertices[(index + 1) % len(vertices)]
        cross = current.x * following.y - following.x * current.y
        cx += (current.x + following.x) * cross
        cy += (current.y + following.y) * cross
    factor = 1.0 / (6.0 * area)
    return Vec2(cx * factor, cy * factor)


def is_convex(vertices: Sequence[Vec2]) -> bool:
    if len(vertices) < 3:
        raise ValueError("a polygon requires at least three vertices")
    sign = 0
    count = len(vertices)
    for index in range(count):
        p0 = vertices[index]
        p1 = vertices[(index + 1) % count]
        p2 = vertices[(index + 2) % count]
        cross = (p1 - p0).cross(p2 - p1)
        if abs(cross) <= 1e-12:
            continue
        current_sign = 1 if cross > 0 else -1
        if sign == 0:
            sign = current_sign
        elif sign != current_sign:
            return False
    return True


def contains_point(vertices: Sequence[Vec2], point: Vec2) -> bool:
    """Even-odd ray cast; boundary points count as inside within float limits."""
    if len(vertices) < 3:
        raise ValueError("a polygon requires at least three vertices")
    inside = False
    count = len(vertices)
    for index in range(count):
        current = vertices[index]
        previous = vertices[index - 1]
        crosses = (current.y > point.y) != (previous.y > point.y)
        if not crosses:
            continue
        intersect_x = (previous.x - current.x) * (point.y - current.y) / (
            previous.y - current.y
        ) + current.x
        if point.x < intersect_x:
            inside = not inside
    return inside
