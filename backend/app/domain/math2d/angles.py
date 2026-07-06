"""Angle helpers. Serialized angles are counterclockwise degrees."""

from __future__ import annotations

import math


def deg_to_rad(degrees: float) -> float:
    return math.radians(degrees)


def rad_to_deg(radians: float) -> float:
    return math.degrees(radians)


def normalize_deg(degrees: float) -> float:
    """Normalize to the half-open interval (-180, 180]."""
    wrapped = math.fmod(degrees, 360.0)
    if wrapped > 180.0:
        wrapped -= 360.0
    elif wrapped <= -180.0:
        wrapped += 360.0
    return wrapped


def shortest_delta_deg(start: float, end: float) -> float:
    """Signed shortest rotation from ``start`` to ``end`` in (-180, 180]."""
    return normalize_deg(end - start)


def lerp_angle_deg(start: float, end: float, t: float) -> float:
    """Interpolate along the shortest arc; 359 to 1 passes through 0."""
    return normalize_deg(start + shortest_delta_deg(start, end) * t)


def clamp(value: float, minimum: float, maximum: float) -> float:
    if minimum > maximum:
        raise ValueError(f"clamp range is inverted: [{minimum}, {maximum}]")
    return max(minimum, min(maximum, value))
