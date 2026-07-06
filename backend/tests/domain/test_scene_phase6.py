from __future__ import annotations

from app.domain.canonical import model_canonical_json
from app.domain.common import TransformSpec
from app.domain.math2d.vec2 import Vec2
from app.domain.project import load_project_document
from app.domain.scene import SceneDefinition, validate_scene
from app.domain.scene_queries import point_query, ray_query, sweep_query
from app.domain.scene_snapshot import build_scene_snapshot
from tests.sample_paths import load_sample


def room_scene() -> SceneDefinition:
    return SceneDefinition.model_validate(
        {
            "id": "scene_room",
            "name": "Room",
            "world_bounds": [-5.0, -1.0, 7.0, 5.0],
            "actors": [
                {
                    "id": "actor_mira",
                    "character_id": "char_biped_alpha",
                    "display_name": "Mira",
                    "root_transform": {"position": [-3.5, 0.0]},
                },
                {
                    "id": "actor_jon",
                    "character_id": "char_biped_beta",
                    "display_name": "Jon",
                    "root_transform": {"position": [4.5, 0.0]},
                    "facing": "left",
                },
            ],
            "objects": [
                {
                    "id": "floor_main",
                    "name": "Floor",
                    "kind": "floor",
                    "bounds": [-5.0, -0.25, 7.0, 0.0],
                    "colliders": [{"type": "box", "center": [1.0, -0.125], "size": [12.0, 0.25]}],
                    "collision_layer": "ground",
                    "walkable": True,
                },
                {
                    "id": "table_main",
                    "name": "Table",
                    "kind": "table",
                    "bounds": [0.0, 0.0, 1.4, 0.9],
                    "colliders": [{"type": "box", "center": [0.7, 0.45], "size": [1.4, 0.9]}],
                    "blocked": True,
                },
                {
                    "id": "chair_main",
                    "name": "Chair",
                    "kind": "chair",
                    "bounds": [2.0, 0.0, 3.0, 1.4],
                    "colliders": [{"type": "box", "center": [2.5, 0.45], "size": [1.0, 0.9]}],
                    "anchors": [
                        {"id": "seat", "position": [2.5, 0.55]},
                        {"id": "back", "position": [2.85, 1.1]},
                    ],
                    "affordances": [
                        {"type": "sit", "anchor_id": "seat"},
                        {"type": "lean", "anchor_id": "back"},
                    ],
                },
                {
                    "id": "door_main",
                    "name": "Door",
                    "kind": "door",
                    "bounds": [5.6, 0.0, 6.0, 2.2],
                    "colliders": [{"type": "box", "center": [5.8, 1.1], "size": [0.4, 2.2]}],
                    "anchors": [{"id": "handle", "position": [5.65, 1.05]}],
                    "affordances": [{"type": "grasp", "anchor_id": "handle"}, {"type": "look_at"}],
                },
            ],
        }
    )


def test_scene_queries_return_known_results() -> None:
    scene = room_scene()
    assert validate_scene(scene) == []
    assert point_query(scene, Vec2(0.7, 0.45))[0].object_id == "table_main"
    ray_hit = ray_query(scene, Vec2(-1.0, 0.45), Vec2(1.0, 0.0), max_distance=4.0)
    assert ray_hit is not None
    assert ray_hit.object_id == "table_main"
    sweep_hit = sweep_query(scene, Vec2(-3.5, 0.2), Vec2(2.5, 0.2), radius=0.2)
    assert sweep_hit is not None
    assert sweep_hit.object_id == "table_main"


def test_scene_snapshot_is_compact_and_byte_stable() -> None:
    project = load_project_document(load_sample("projects/biped-demo.rigstory.json")).document
    characters = {character.id: character for character in project.characters}
    snapshot = build_scene_snapshot(room_scene(), characters=characters)
    first = model_canonical_json(snapshot)
    second = model_canonical_json(build_scene_snapshot(room_scene(), characters=characters))
    assert first == second
    assert len(first.encode("utf-8")) < 5000
    assert "path" not in first.lower()
    assert "texture" not in first.lower()
    assert snapshot.walkable_regions == ("floor_main",)
    assert "chair_main.seat" in {item.anchor_ref for item in snapshot.reachability}


def test_scene_validation_flags_blocked_start_overlap_and_missing_ground() -> None:
    base = room_scene()
    blocked_actor = base.actors[0].model_copy(
        update={"root_transform": TransformSpec(position=(0.7, 0.45))}
    )
    blocked = base.model_copy(update={"actors": (blocked_actor, base.actors[1])})
    assert "SCENE_ACTOR_IN_BLOCKED_REGION" in {issue.code for issue in validate_scene(blocked)}

    overlap_actor = base.actors[1].model_copy(
        update={"root_transform": TransformSpec(position=(-3.4, 0.0))}
    )
    overlap = base.model_copy(update={"actors": (base.actors[0], overlap_actor)})
    assert "SCENE_ACTORS_OVERLAP" in {issue.code for issue in validate_scene(overlap)}

    no_ground = base.model_copy(
        update={"objects": tuple(obj for obj in base.objects if obj.id != "floor_main")}
    )
    assert "SCENE_MISSING_GROUND" in {issue.code for issue in validate_scene(no_ground)}
