"""Migration registry for versioned persisted documents.

Migrations operate on raw JSON dictionaries because an older document may not
validate against the current Pydantic schema. Each step transforms one
released version into the next; the registry chains steps until the target
version is reached. Unknown fields are carried through untouched so future
data survives a round trip where practical.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.domain.canonical import JsonValue
from app.domain.versioning import PROJECT_SCHEMA_VERSION, SchemaVersion

type JsonDocument = dict[str, JsonValue]
type MigrationFn = Callable[[JsonDocument], JsonDocument]


class MigrationError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class MigrationResult:
    document: JsonDocument
    applied: tuple[str, ...]
    from_version: str
    to_version: str


class MigrationRegistry:
    """Orders and applies single-step migrations between released versions."""

    def __init__(self, document_kind: str) -> None:
        self._document_kind = document_kind
        self._steps: dict[SchemaVersion, tuple[SchemaVersion, MigrationFn]] = {}

    def register(self, from_version: str, to_version: str) -> Callable[[MigrationFn], MigrationFn]:
        source = SchemaVersion.parse(from_version)
        target = SchemaVersion.parse(to_version)
        if target <= source:
            raise MigrationError(f"migration must increase version: {source} -> {target}")
        if source in self._steps:
            raise MigrationError(f"duplicate migration registered from {source}")

        def decorator(fn: MigrationFn) -> MigrationFn:
            self._steps[source] = (target, fn)
            return fn

        return decorator

    def migrate(self, document: JsonDocument, target: SchemaVersion) -> MigrationResult:
        raw_version = document.get("schema_version")
        if not isinstance(raw_version, str):
            raise MigrationError(f"{self._document_kind} document has no schema_version")
        current = SchemaVersion.parse(raw_version)
        if current > target:
            raise MigrationError(
                f"{self._document_kind} version {current} is newer than supported {target}"
            )
        source = current
        applied: list[str] = []
        while current < target:
            step = self._steps.get(current)
            if step is None:
                raise MigrationError(
                    f"no migration path from {self._document_kind} version {current} to {target}"
                )
            next_version, fn = step
            document = fn(dict(document))
            document["schema_version"] = str(next_version)
            applied.append(f"{current}->{next_version}")
            current = next_version
        return MigrationResult(
            document=document,
            applied=tuple(applied),
            from_version=str(source),
            to_version=str(current),
        )


project_migrations = MigrationRegistry("project")


@project_migrations.register("0.1.0", "0.2.0")
def _project_0_1_0_to_0_2_0(document: JsonDocument) -> JsonDocument:
    # 0.2.0 introduced item schemas for characters, scenes, and clips.
    # 0.1.0 documents only ever contained empty collections, so the document
    # is structurally unchanged; the version bump is recorded by the registry.
    return document


@project_migrations.register("0.2.0", "0.3.0")
def _project_0_2_0_to_0_3_0(document: JsonDocument) -> JsonDocument:
    # 0.3.0 replaced the reserved empty ``generation_records`` placeholder with a
    # real item schema. 0.2.0 documents only ever stored an empty list,
    # which remains valid, so no data transformation is required.
    document.setdefault("generation_records", [])
    return document


@project_migrations.register("0.3.0", "0.4.0")
def _project_0_3_0_to_0_4_0(document: JsonDocument) -> JsonDocument:
    # 0.4.0 makes scene object visuals and editor/query flags explicit. Older
    # scene objects already had bounds and collider semantics, so defaults can
    # be derived without changing their behavior.
    scenes = document.get("scenes", [])
    if not isinstance(scenes, list):
        return document
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        objects = scene.get("objects", [])
        if not isinstance(objects, list):
            continue
        for scene_object in objects:
            if not isinstance(scene_object, dict):
                continue
            scene_object.setdefault("visual", {"type": "rectangle"})
            scene_object.setdefault("visible", True)
            scene_object.setdefault("locked", False)
            layer = scene_object.get("collision_layer")
            mask: list[JsonValue] = [layer] if isinstance(layer, str) else ["default"]
            scene_object.setdefault("collision_mask", mask)
            kind = scene_object.get("kind")
            layer_text = layer if isinstance(layer, str) else ""
            scene_object.setdefault("walkable", kind == "floor" or layer_text == "ground")
            scene_object.setdefault("blocked", False)
    return document


@project_migrations.register("0.4.0", "0.5.0")
def _project_0_4_0_to_0_5_0(document: JsonDocument) -> JsonDocument:
    # 0.5.0 replaced the reserved empty ``motion_plans`` placeholder with a real
    # item schema and added optional plan provenance to clips. 0.4.0
    # documents only ever stored an empty plan list, which remains valid; older
    # clips simply have no source plan.
    document.setdefault("motion_plans", [])
    clips = document.get("clips", [])
    if isinstance(clips, list):
        for clip in clips:
            if isinstance(clip, dict):
                clip.setdefault("source_plan_id", None)
                clip.setdefault("engine_version", None)
    return document


@project_migrations.register("0.5.0", "0.6.0")
def _project_0_5_0_to_0_6_0(document: JsonDocument) -> JsonDocument:
    # 0.6.0 adds optional weighted mesh payloads to attachments. Existing
    # primitive/svg/png attachments remain valid with no data transformation.
    return document


def migrate_project_document(document: JsonDocument) -> MigrationResult:
    return project_migrations.migrate(document, PROJECT_SCHEMA_VERSION)
