"""Validate every shared sample against the backend domain schemas.

- ``samples/projects/*.rigstory.json`` must load cleanly (migrate + parse +
  invariants).
- ``samples/fixtures/rig-*.json`` and ``scene-*.json`` must parse and pass
  invariant validation.
- ``samples/migrations/*.rigstory.json`` are older released versions and must
  migrate to the current schema version cleanly.
- ``samples/invalid/*.json`` must be rejected; a silently accepted invalid
  sample fails this script.

Requires the backend package importable (run ``pip install -e backend`` or
execute from a checkout; the script adds ``backend/`` to ``sys.path``).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from pydantic import ValidationError  # noqa: E402

from app.domain.canonical import JsonValue  # noqa: E402
from app.domain.errors import DomainValidationError  # noqa: E402
from app.domain.migrations import MigrationError  # noqa: E402
from app.domain.project import load_project_document  # noqa: E402
from app.domain.rig import RigDefinition, validate_rig  # noqa: E402
from app.domain.scene import SceneDefinition, validate_scene  # noqa: E402

SAMPLES = ROOT / "samples"


def _read(path: Path) -> dict[str, JsonValue]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SystemExit(f"{path}: expected a JSON object at the top level")
    return raw


def _ok(path: Path, note: str = "") -> None:
    suffix = f" ({note})" if note else ""
    print(f"validated {path.relative_to(ROOT)}{suffix}")


def validate_projects() -> None:
    paths = sorted((SAMPLES / "projects").glob("*.rigstory.json"))
    if not paths:
        raise SystemExit("No project samples found.")
    for path in paths:
        loaded = load_project_document(_read(path))
        note = ", ".join(loaded.migration.applied)
        _ok(path, f"migrated {note}" if note else "")


def validate_fixtures() -> None:
    fixtures = SAMPLES / "fixtures"
    for path in sorted(fixtures.glob("rig-*.json")):
        rig = RigDefinition.model_validate(_read(path))
        issues = validate_rig(rig)
        if issues:
            raise SystemExit(f"{path}: {[str(issue) for issue in issues]}")
        _ok(path)
    for path in sorted(fixtures.glob("scene-*.json")):
        scene = SceneDefinition.model_validate(_read(path))
        issues = validate_scene(scene)
        if issues:
            raise SystemExit(f"{path}: {[str(issue) for issue in issues]}")
        _ok(path)


def validate_migrations() -> None:
    for path in sorted((SAMPLES / "migrations").glob("*.rigstory.json")):
        loaded = load_project_document(_read(path))
        if not loaded.migration.applied:
            raise SystemExit(f"{path}: expected at least one migration step")
        _ok(path, f"migrated {', '.join(loaded.migration.applied)}")


def check_invalid_samples() -> None:
    paths = sorted((SAMPLES / "invalid").glob("*.json"))
    if not paths:
        raise SystemExit("No invalid samples found.")
    for path in paths:
        raw = _read(path)
        try:
            if path.name.startswith("rig-"):
                rig = RigDefinition.model_validate(raw)
                issues = validate_rig(rig)
                if issues:
                    raise DomainValidationError(tuple(issues))
            else:
                load_project_document(raw)
        except (ValidationError, DomainValidationError, MigrationError) as error:
            kind = type(error).__name__
            _ok(path, f"rejected as expected: {kind}")
        else:
            raise SystemExit(f"{path}: invalid sample was accepted")


def main() -> None:
    validate_projects()
    validate_fixtures()
    validate_migrations()
    check_invalid_samples()


if __name__ == "__main__":
    main()
