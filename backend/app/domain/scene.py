"""Scene definition: actor instances, objects, colliders, anchors, affordances.

A scene holds at most two actor instances (ADR 0006). The limit is enforced
at the schema level so no document with more than two actors can exist.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.domain.common import Bounds4, DomainModel, Point2, TransformSpec, bounds_are_valid
from app.domain.errors import ValidationIssue
from app.domain.ids import ActorId, AnchorId, AssetId, CharacterId, ObjectId, SceneId
from app.domain.math2d.polygon import is_convex, signed_area
from app.domain.math2d.vec2 import Vec2

MAX_ACTORS_PER_SCENE = 2

AFFORDANCE_TYPES = ("sit", "stand_on", "grasp", "lean", "look_at", "avoid")
type AffordanceType = Literal["sit", "stand_on", "grasp", "lean", "look_at", "avoid"]

# Affordances an actor performs at a specific point need a named anchor.
ANCHOR_REQUIRED_AFFORDANCES = frozenset({"sit", "stand_on", "grasp", "lean"})


class BoxCollider(DomainModel):
    type: Literal["box"] = "box"
    center: Point2 = (0.0, 0.0)
    size: Point2
    rotation_deg: float = 0.0


class CircleCollider(DomainModel):
    type: Literal["circle"] = "circle"
    center: Point2 = (0.0, 0.0)
    radius: float = Field(gt=0.0)


class CapsuleCollider(DomainModel):
    type: Literal["capsule"] = "capsule"
    point_a: Point2
    point_b: Point2
    radius: float = Field(gt=0.0)


class PolygonCollider(DomainModel):
    type: Literal["polygon"] = "polygon"
    vertices: tuple[Point2, ...] = Field(min_length=3)


type Collider = Annotated[
    BoxCollider | CircleCollider | CapsuleCollider | PolygonCollider,
    Field(discriminator="type"),
]


class RectangleVisual(DomainModel):
    type: Literal["rectangle"] = "rectangle"
    fill: str = Field(default="#d8dee9", pattern=r"^#[0-9a-fA-F]{6}$")
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)


class PolygonVisual(DomainModel):
    type: Literal["polygon"] = "polygon"
    vertices: tuple[Point2, ...] = Field(min_length=3)
    fill: str = Field(default="#d8dee9", pattern=r"^#[0-9a-fA-F]{6}$")
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)


class SvgVisual(DomainModel):
    type: Literal["svg"] = "svg"
    asset_id: AssetId
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)


class PngVisual(DomainModel):
    type: Literal["png"] = "png"
    asset_id: AssetId
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)


type ObjectVisual = Annotated[
    RectangleVisual | PolygonVisual | SvgVisual | PngVisual,
    Field(discriminator="type"),
]


class Anchor(DomainModel):
    """Named interaction point local to its owning object."""

    id: AnchorId
    position: Point2
    rotation_deg: float = 0.0


class Affordance(DomainModel):
    type: AffordanceType
    anchor_id: AnchorId | None = None


class SceneObject(DomainModel):
    id: ObjectId
    name: str = Field(min_length=1)
    kind: str = Field(min_length=1, description="Semantic label such as 'chair' or 'floor'.")
    transform: TransformSpec = TransformSpec()
    bounds: Bounds4
    visual: ObjectVisual = RectangleVisual()
    colliders: tuple[Collider, ...] = ()
    anchors: tuple[Anchor, ...] = ()
    affordances: tuple[Affordance, ...] = ()
    collision_layer: str = "default"
    collision_mask: tuple[str, ...] = ("default",)
    body_type: Literal["static", "kinematic", "decorative"] = "static"
    visible: bool = True
    locked: bool = False
    walkable: bool = False
    blocked: bool = False


class ActorInstance(DomainModel):
    id: ActorId
    character_id: CharacterId
    display_name: str = Field(min_length=1)
    root_transform: TransformSpec = TransformSpec()
    facing: Literal["left", "right"] = "right"
    state: str = Field(default="standing", pattern=r"^[a-z][a-z0-9_]*$")


class SceneDefinition(DomainModel):
    id: SceneId
    name: str = Field(min_length=1)
    world_bounds: Bounds4
    ground_y: float = 0.0
    actors: tuple[ActorInstance, ...] = Field(default=(), max_length=MAX_ACTORS_PER_SCENE)
    objects: tuple[SceneObject, ...] = ()

    @model_validator(mode="after")
    def _check_actor_count(self) -> SceneDefinition:
        if len(self.actors) > MAX_ACTORS_PER_SCENE:
            raise ValueError(f"a scene may contain at most {MAX_ACTORS_PER_SCENE} actors")
        return self


def validate_scene(scene: SceneDefinition, path_prefix: str = "") -> list[ValidationIssue]:
    prefix = f"{path_prefix}." if path_prefix else ""
    issues: list[ValidationIssue] = []

    if not bounds_are_valid(scene.world_bounds):
        issues.append(
            ValidationIssue(
                "SCENE_INVALID_BOUNDS",
                f"world bounds min exceeds max: {list(scene.world_bounds)}",
                f"{prefix}world_bounds",
            )
        )

    seen_actor_ids: set[str] = set()
    for index, actor in enumerate(scene.actors):
        if actor.id in seen_actor_ids:
            issues.append(
                ValidationIssue(
                    "SCENE_DUPLICATE_ACTOR_ID",
                    f"actor id {actor.id!r} is defined more than once",
                    f"{prefix}actors[{index}].id",
                )
            )
        seen_actor_ids.add(actor.id)

    for left_index, left in enumerate(scene.actors):
        left_pos = Vec2(left.root_transform.position[0], left.root_transform.position[1])
        for right_index, right in enumerate(scene.actors[left_index + 1 :], start=left_index + 1):
            right_pos = Vec2(right.root_transform.position[0], right.root_transform.position[1])
            if left_pos.distance_to(right_pos) < 0.35:
                issues.append(
                    ValidationIssue(
                        "SCENE_ACTORS_OVERLAP",
                        f"actors {left.id!r} and {right.id!r} start too close together",
                        f"{prefix}actors[{right_index}].root_transform.position",
                    )
                )

    seen_object_ids: set[str] = set()
    for obj_index, obj in enumerate(scene.objects):
        object_path = f"{prefix}objects[{obj_index}]"
        if obj.id in seen_object_ids:
            issues.append(
                ValidationIssue(
                    "SCENE_DUPLICATE_OBJECT_ID",
                    f"object id {obj.id!r} is defined more than once",
                    f"{object_path}.id",
                )
            )
        seen_object_ids.add(obj.id)

        if not bounds_are_valid(obj.bounds):
            issues.append(
                ValidationIssue(
                    "SCENE_INVALID_BOUNDS",
                    f"object {obj.id!r} bounds min exceeds max: {list(obj.bounds)}",
                    f"{object_path}.bounds",
                )
            )

        anchor_ids: set[str] = set()
        for anchor_index, anchor in enumerate(obj.anchors):
            if anchor.id in anchor_ids:
                issues.append(
                    ValidationIssue(
                        "SCENE_DUPLICATE_ANCHOR_ID",
                        f"object {obj.id!r} defines anchor {anchor.id!r} more than once",
                        f"{object_path}.anchors[{anchor_index}].id",
                    )
                )
            anchor_ids.add(anchor.id)

        for affordance_index, affordance in enumerate(obj.affordances):
            affordance_path = f"{object_path}.affordances[{affordance_index}]"
            if affordance.type in ANCHOR_REQUIRED_AFFORDANCES and affordance.anchor_id is None:
                issues.append(
                    ValidationIssue(
                        "SCENE_AFFORDANCE_MISSING_ANCHOR",
                        f"affordance {affordance.type!r} on object {obj.id!r} "
                        "requires an anchor_id",
                        f"{affordance_path}.anchor_id",
                    )
                )
            elif affordance.anchor_id is not None and affordance.anchor_id not in anchor_ids:
                issues.append(
                    ValidationIssue(
                        "SCENE_AFFORDANCE_UNKNOWN_ANCHOR",
                        f"affordance {affordance.type!r} on object {obj.id!r} references "
                        f"unknown anchor {affordance.anchor_id!r}",
                        f"{affordance_path}.anchor_id",
                    )
                )

        for collider_index, collider in enumerate(obj.colliders):
            if collider.type == "box" and (collider.size[0] <= 0.0 or collider.size[1] <= 0.0):
                issues.append(
                    ValidationIssue(
                        "SCENE_INVALID_COLLIDER",
                        f"box collider on object {obj.id!r} must have positive size",
                        f"{object_path}.colliders[{collider_index}].size",
                    )
                )
            if collider.type == "polygon":
                vertices = [Vec2(x, y) for x, y in collider.vertices]
                if abs(signed_area(vertices)) <= 1e-9:
                    issues.append(
                        ValidationIssue(
                            "SCENE_DEGENERATE_POLYGON",
                            f"polygon collider on object {obj.id!r} has near-zero area",
                            f"{object_path}.colliders[{collider_index}].vertices",
                        )
                    )
                elif not is_convex(vertices):
                    issues.append(
                        ValidationIssue(
                            "SCENE_NONCONVEX_POLYGON",
                            f"polygon collider on object {obj.id!r} is not convex",
                            f"{object_path}.colliders[{collider_index}].vertices",
                        )
                    )
        if obj.visual.type == "polygon":
            vertices = [Vec2(x, y) for x, y in obj.visual.vertices]
            if abs(signed_area(vertices)) <= 1e-9:
                issues.append(
                    ValidationIssue(
                        "SCENE_DEGENERATE_VISUAL_POLYGON",
                        f"polygon visual on object {obj.id!r} has near-zero area",
                        f"{object_path}.visual.vertices",
                    )
                )
    if (
        scene.actors
        and scene.objects
        and not any(
            obj.walkable or obj.kind == "floor" or obj.collision_layer == "ground"
            for obj in scene.objects
        )
    ):
        issues.append(
            ValidationIssue(
                "SCENE_MISSING_GROUND",
                "scene has no walkable surface",
                f"{prefix}objects",
            )
        )
    blocked_objects = {obj.id for obj in scene.objects if obj.blocked}
    if blocked_objects:
        from app.domain.scene_queries import point_query

        for actor_index, actor in enumerate(scene.actors):
            position = Vec2(actor.root_transform.position[0], actor.root_transform.position[1])
            hits = point_query(scene, position)
            if any(hit.object_id in blocked_objects for hit in hits):
                issues.append(
                    ValidationIssue(
                        "SCENE_ACTOR_IN_BLOCKED_REGION",
                        f"actor {actor.id!r} starts inside a blocked region",
                        f"{prefix}actors[{actor_index}].root_transform.position",
                    )
                )
    return issues
