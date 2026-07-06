"""Cubic Bezier evaluation."""

from __future__ import annotations

from app.domain.math2d.vec2 import Vec2


def cubic_scalar(p0: float, p1: float, p2: float, p3: float, t: float) -> float:
    u = 1.0 - t
    return u * u * u * p0 + 3.0 * u * u * t * p1 + 3.0 * u * t * t * p2 + t * t * t * p3


def cubic_scalar_derivative(p0: float, p1: float, p2: float, p3: float, t: float) -> float:
    u = 1.0 - t
    return 3.0 * u * u * (p1 - p0) + 6.0 * u * t * (p2 - p1) + 3.0 * t * t * (p3 - p2)


def cubic_point(p0: Vec2, p1: Vec2, p2: Vec2, p3: Vec2, t: float) -> Vec2:
    return Vec2(
        cubic_scalar(p0.x, p1.x, p2.x, p3.x, t),
        cubic_scalar(p0.y, p1.y, p2.y, p3.y, t),
    )


def cubic_point_derivative(p0: Vec2, p1: Vec2, p2: Vec2, p3: Vec2, t: float) -> Vec2:
    return Vec2(
        cubic_scalar_derivative(p0.x, p1.x, p2.x, p3.x, t),
        cubic_scalar_derivative(p0.y, p1.y, p2.y, p3.y, t),
    )
