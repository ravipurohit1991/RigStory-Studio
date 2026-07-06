"""Compact semantic scene snapshots for motion planning."""

from __future__ import annotations

from itertools import combinations

from pydantic import Field

from app.domain.canonical import model_canonical_json
from app.domain.character import CharacterDefinition
from app.domain.common import Bounds4, DomainModel, Point2
from app.domain.math2d.vec2 import Vec2
from app.domain.scene import SceneDefinition
from app.domain.scene_queries import object_world_bounds, point_query

SNAPSHOT_SCHEMA_VERSION = "1.0.0"


class SnapshotActor(DomainModel):
    id: str
    character_id: str
    display_name: str
    position: Point2
    facing: str
    state: str
    reach_radius: float
    blocked_at_start: bool


class SnapshotAnchor(DomainModel):
    id: str
    ref: str
    position: Point2
    rotation_deg: float


class SnapshotAffordance(DomainModel):
    type: str
    anchor_ref: str | None = None


class SnapshotObject(DomainModel):
    id: str
    name: str
    kind: str
    bounds: Bounds4
    collider_count: int
    collision_layer: str
    walkable: bool
    blocked: bool
    anchors: tuple[SnapshotAnchor, ...] = ()
    affordances: tuple[SnapshotAffordance, ...] = ()


class SnapshotRelation(DomainModel):
    subject_id: str
    relation: str
    object_id: str
    distance: float = Field(ge=0.0)


class SnapshotReachability(DomainModel):
    actor_id: str
    anchor_ref: str
    distance: float
    reachable: bool


class SceneSnapshot(DomainModel):
    schema_version: str = SNAPSHOT_SCHEMA_VERSION
    scene_id: str
    scene_name: str
    world_bounds: Bounds4
    coordinate_system: str = "Y-up, counterclockwise degrees"
    actors: tuple[SnapshotActor, ...]
    objects: tuple[SnapshotObject, ...]
    walkable_regions: tuple[str, ...]
    blocked_regions: tuple[str, ...]
    relations: tuple[SnapshotRelation, ...]
    reachability: tuple[SnapshotReachability, ...]

    def canonical_json(self) -> str:
        return model_canonical_json(self)


def _point(value: tuple[float, float]) -> Vec2:
    return Vec2(value[0], value[1])


def _rig_reach_radius(character: CharacterDefinition | None) -> float:
    if character is None:
        return 1.0
    lengths = {bone.id: bone.length for bone in character.rig.bones}
    arm_lengths = [
        lengths.get("upper_arm_l", 0.0)
        + lengths.get("forearm_l", 0.0)
        + lengths.get("hand_l", 0.0),
        lengths.get("upper_arm_r", 0.0)
        + lengths.get("forearm_r", 0.0)
        + lengths.get("hand_r", 0.0),
    ]
    return max([1.0, *arm_lengths])


def build_scene_snapshot(
    scene: SceneDefinition,
    *,
    characters: dict[str, CharacterDefinition] | None = None,
) -> SceneSnapshot:
    characters = characters or {}
    actors: list[SnapshotActor] = []
    actor_positions: dict[str, Vec2] = {}
    for actor in sorted(scene.actors, key=lambda item: item.id):
        position = _point(actor.root_transform.position)
        actor_positions[actor.id] = position
        reach_radius = _rig_reach_radius(characters.get(actor.character_id))
        actors.append(
            SnapshotActor(
                id=actor.id,
                character_id=actor.character_id,
                display_name=actor.display_name,
                position=actor.root_transform.position,
                facing=actor.facing,
                state=actor.state,
                reach_radius=round(reach_radius, 4),
                blocked_at_start=bool(point_query(scene, position)),
            )
        )

    objects: list[SnapshotObject] = []
    anchors_by_ref: dict[str, Vec2] = {}
    for scene_object in sorted(scene.objects, key=lambda item: item.id):
        matrix = scene_object.transform.to_transform2d().to_affine()
        anchors: list[SnapshotAnchor] = []
        for anchor in sorted(scene_object.anchors, key=lambda item: item.id):
            world_position = matrix.apply_point(_point(anchor.position))
            ref = f"{scene_object.id}.{anchor.id}"
            anchors_by_ref[ref] = world_position
            anchors.append(
                SnapshotAnchor(
                    id=anchor.id,
                    ref=ref,
                    position=(round(world_position.x, 4), round(world_position.y, 4)),
                    rotation_deg=scene_object.transform.rotation_deg + anchor.rotation_deg,
                )
            )
        bounds = object_world_bounds(scene_object)
        objects.append(
            SnapshotObject(
                id=scene_object.id,
                name=scene_object.name,
                kind=scene_object.kind,
                bounds=(
                    round(bounds.min_x, 4),
                    round(bounds.min_y, 4),
                    round(bounds.max_x, 4),
                    round(bounds.max_y, 4),
                ),
                collider_count=len(scene_object.colliders),
                collision_layer=scene_object.collision_layer,
                walkable=scene_object.walkable
                or scene_object.kind == "floor"
                or scene_object.collision_layer == "ground",
                blocked=scene_object.blocked,
                anchors=tuple(anchors),
                affordances=tuple(
                    SnapshotAffordance(
                        type=affordance.type,
                        anchor_ref=(
                            f"{scene_object.id}.{affordance.anchor_id}"
                            if affordance.anchor_id is not None
                            else None
                        ),
                    )
                    for affordance in sorted(
                        scene_object.affordances,
                        key=lambda item: (item.type, item.anchor_id or ""),
                    )
                ),
            )
        )

    relations: list[SnapshotRelation] = []
    for left, right in combinations(sorted(actor_positions), 2):
        left_pos = actor_positions[left]
        right_pos = actor_positions[right]
        distance = round(left_pos.distance_to(right_pos), 4)
        relation = "left_of" if left_pos.x < right_pos.x else "right_of"
        relations.append(
            SnapshotRelation(
                subject_id=left,
                relation=relation,
                object_id=right,
                distance=distance,
            )
        )

    reachability: list[SnapshotReachability] = []
    for snapshot_actor in actors:
        actor_position = actor_positions[snapshot_actor.id]
        for ref, anchor_position in sorted(anchors_by_ref.items()):
            distance = round(actor_position.distance_to(anchor_position), 4)
            reachability.append(
                SnapshotReachability(
                    actor_id=snapshot_actor.id,
                    anchor_ref=ref,
                    distance=distance,
                    reachable=distance <= snapshot_actor.reach_radius,
                )
            )

    return SceneSnapshot(
        scene_id=scene.id,
        scene_name=scene.name,
        world_bounds=scene.world_bounds,
        actors=tuple(actors),
        objects=tuple(objects),
        walkable_regions=tuple(obj.id for obj in objects if obj.walkable),
        blocked_regions=tuple(obj.id for obj in objects if obj.blocked),
        relations=tuple(sorted(relations, key=lambda item: (item.subject_id, item.object_id))),
        reachability=tuple(sorted(reachability, key=lambda item: (item.actor_id, item.anchor_ref))),
    )
