"""Deterministic scene spatial queries.

Queries operate on the native scene model in Y-up coordinates. They are simple
kinematic helpers, not a physics engine, and are intentionally deterministic so
snapshots and compiler validation can be reproduced byte-for-byte.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.math2d.aabb import Aabb
from app.domain.math2d.affine import Affine2
from app.domain.math2d.polygon import contains_point
from app.domain.math2d.vec2 import Vec2
from app.domain.scene import Collider, SceneDefinition, SceneObject


@dataclass(frozen=True, slots=True)
class ColliderHit:
    object_id: str
    collider_index: int
    point: Vec2
    distance: float = 0.0


def _point(value: tuple[float, float]) -> Vec2:
    return Vec2(value[0], value[1])


def object_world_matrix(scene_object: SceneObject) -> Affine2:
    return scene_object.transform.to_transform2d().to_affine()


def object_world_bounds(scene_object: SceneObject) -> Aabb:
    min_x, min_y, max_x, max_y = scene_object.bounds
    matrix = object_world_matrix(scene_object)
    return Aabb.from_points(
        matrix.apply_point(point)
        for point in (
            Vec2(min_x, min_y),
            Vec2(max_x, min_y),
            Vec2(max_x, max_y),
            Vec2(min_x, max_y),
        )
    )


def collider_world_bounds(scene_object: SceneObject, collider: Collider) -> Aabb:
    matrix = object_world_matrix(scene_object)
    if collider.type == "box":
        center = _point(collider.center)
        half = Vec2(collider.size[0] / 2.0, collider.size[1] / 2.0)
        corners = (
            Vec2(center.x - half.x, center.y - half.y),
            Vec2(center.x + half.x, center.y - half.y),
            Vec2(center.x + half.x, center.y + half.y),
            Vec2(center.x - half.x, center.y + half.y),
        )
        rotated = [
            center + (corner - center).rotated_deg(collider.rotation_deg) for corner in corners
        ]
        return Aabb.from_points(matrix.apply_point(point) for point in rotated)
    if collider.type == "circle":
        center = matrix.apply_point(_point(collider.center))
        radius = collider.radius * max(
            abs(scene_object.transform.scale[0]), abs(scene_object.transform.scale[1])
        )
        return Aabb(center.x - radius, center.y - radius, center.x + radius, center.y + radius)
    if collider.type == "capsule":
        a = matrix.apply_point(_point(collider.point_a))
        b = matrix.apply_point(_point(collider.point_b))
        radius = collider.radius * max(
            abs(scene_object.transform.scale[0]), abs(scene_object.transform.scale[1])
        )
        return Aabb.from_points((a, b)).expanded(radius)
    return Aabb.from_points(matrix.apply_point(_point(point)) for point in collider.vertices)


def _distance_to_segment(point: Vec2, a: Vec2, b: Vec2) -> float:
    ab = b - a
    length_sq = ab.length_squared()
    if length_sq <= 1e-12:
        return point.distance_to(a)
    t = max(0.0, min(1.0, (point - a).dot(ab) / length_sq))
    closest = a + ab.scaled(t)
    return point.distance_to(closest)


def point_in_collider(scene_object: SceneObject, collider: Collider, point: Vec2) -> bool:
    inverse = object_world_matrix(scene_object).inverse()
    local = inverse.apply_point(point)
    if collider.type == "box":
        center = _point(collider.center)
        unrotated = center + (local - center).rotated_deg(-collider.rotation_deg)
        return (
            abs(unrotated.x - center.x) <= collider.size[0] / 2.0 + 1e-9
            and abs(unrotated.y - center.y) <= collider.size[1] / 2.0 + 1e-9
        )
    if collider.type == "circle":
        return local.distance_to(_point(collider.center)) <= collider.radius + 1e-9
    if collider.type == "capsule":
        return (
            _distance_to_segment(local, _point(collider.point_a), _point(collider.point_b))
            <= collider.radius + 1e-9
        )
    return contains_point([_point(vertex) for vertex in collider.vertices], local)


def point_query(
    scene: SceneDefinition,
    point: Vec2,
    *,
    include_decorative: bool = False,
) -> tuple[ColliderHit, ...]:
    hits: list[ColliderHit] = []
    for scene_object in scene.objects:
        if not scene_object.visible:
            continue
        if scene_object.body_type == "decorative" and not include_decorative:
            continue
        for index, collider in enumerate(scene_object.colliders):
            if point_in_collider(scene_object, collider, point):
                hits.append(ColliderHit(scene_object.id, index, point))
    return tuple(sorted(hits, key=lambda hit: (hit.object_id, hit.collider_index)))


def ray_query(
    scene: SceneDefinition,
    origin: Vec2,
    direction: Vec2,
    *,
    max_distance: float,
    steps: int = 128,
) -> ColliderHit | None:
    if max_distance <= 0.0:
        return None
    unit = direction.normalized()
    sample_count = max(1, steps)
    for step in range(sample_count + 1):
        distance = max_distance * step / sample_count
        point = origin + unit.scaled(distance)
        hits = point_query(scene, point)
        if hits:
            hit = hits[0]
            return ColliderHit(hit.object_id, hit.collider_index, point, distance)
    return None


def sweep_query(
    scene: SceneDefinition,
    start: Vec2,
    end: Vec2,
    *,
    radius: float,
    steps: int = 128,
) -> ColliderHit | None:
    blocking_ids = {
        scene_object.id
        for scene_object in scene.objects
        if not scene_object.walkable
        and scene_object.kind != "floor"
        and scene_object.collision_layer != "ground"
    }
    sample_count = max(1, steps)
    for step in range(sample_count + 1):
        t = step / sample_count
        center = start.lerp(end, t)
        if radius <= 0.0:
            hits = point_query(scene, center)
        else:
            offsets = (
                Vec2.zero(),
                Vec2(radius, 0.0),
                Vec2(-radius, 0.0),
                Vec2(0.0, radius),
                Vec2(0.0, -radius),
            )
            hits = tuple(hit for offset in offsets for hit in point_query(scene, center + offset))
        hits = tuple(hit for hit in hits if hit.object_id in blocking_ids)
        if hits:
            hit = hits[0]
            return ColliderHit(hit.object_id, hit.collider_index, center, start.distance_to(center))
    return None


def blocked_objects(scene: SceneDefinition) -> tuple[SceneObject, ...]:
    return tuple(
        scene_object
        for scene_object in scene.objects
        if scene_object.blocked or (scene_object.colliders and not scene_object.walkable)
    )
