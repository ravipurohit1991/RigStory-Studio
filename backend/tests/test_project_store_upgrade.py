from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from app.domain.canonical import JsonValue, canonical_json_pretty
from app.domain.versioning import PROJECT_SCHEMA_VERSION
from app.services.project_store import FileProjectStore
from tests.sample_paths import load_sample

type JsonObject = dict[str, JsonValue]


def _plant_legacy_project(root: Path, raw: JsonObject) -> str:
    """Write an older-version document directly, as a pre-upgrade install would have."""
    project = cast(JsonObject, raw["project"])
    project_id = str(project["id"])
    project_dir = root / "projects" / project_id
    (project_dir / "revisions").mkdir(parents=True)
    text = canonical_json_pretty(raw)
    (project_dir / "current.json").write_text(text, encoding="utf-8")
    (project_dir / "revisions" / "000001-rev_legacy.json").write_text(text, encoding="utf-8")
    (project_dir / "metadata.json").write_text(
        json.dumps(
            {
                "project_id": project_id,
                "current_revision": "rev_legacy",
                "revision_sequence": 1,
                "last_good_revision": "rev_legacy",
            }
        ),
        encoding="utf-8",
    )
    return project_id


def test_opening_a_legacy_project_backs_up_then_upgrades_in_place(tmp_path: Path) -> None:
    raw = load_sample("migrations/walker-project-0.3.0.rigstory.json")
    store = FileProjectStore(tmp_path)
    project_id = _plant_legacy_project(tmp_path, raw)

    stored = store.get_project(project_id)

    # The returned document is at the current schema version.
    assert stored.document.schema_version == str(PROJECT_SCHEMA_VERSION)
    assert stored.revision != "rev_legacy"

    # The original bytes are preserved as a backup before the upgrade.
    backups = list((tmp_path / "projects" / project_id / "backups").glob("*.json"))
    assert len(backups) == 1
    assert "pre-upgrade-0.3.0" in backups[0].name
    backup_raw = cast(JsonObject, json.loads(backups[0].read_text(encoding="utf-8")))
    assert backup_raw["schema_version"] == "0.3.0"

    # current.json is upgraded in place and re-reading is a plain read.
    current_raw = cast(
        JsonObject,
        json.loads(
            (tmp_path / "projects" / project_id / "current.json").read_text(encoding="utf-8")
        ),
    )
    assert current_raw["schema_version"] == str(PROJECT_SCHEMA_VERSION)
    reread = store.get_project(project_id)
    assert reread.revision == stored.revision
    backups_after = list((tmp_path / "projects" / project_id / "backups").glob("*.json"))
    assert len(backups_after) == 1


def test_current_version_project_is_not_backed_up(tmp_path: Path) -> None:
    store = FileProjectStore(tmp_path)
    created = store.create_project(name="Fresh")
    stored = store.get_project(created.document.project.id)
    assert stored.revision == created.revision
    assert not (tmp_path / "projects" / created.document.project.id / "backups").exists()
