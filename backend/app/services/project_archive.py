"""Portable project archive export and import.

An archive is a zip file with three kinds of entries:

- ``manifest.json`` — archive format/version, project identity, and a checksum
  for every other entry;
- ``project.json`` — the canonical project document;
- ``assets/sha256/ab/cd/<hash>`` — content-addressed asset payloads.

Import never extracts to disk paths taken from the archive: every entry name is
validated against an allowlist shape, all payloads are read into memory with a
size budget, and each checksum in the manifest must match before any document
or asset is accepted. Older documents are migrated through the registered
schema chain and the applied steps are reported to the caller.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.domain.canonical import JsonValue, canonical_json_pretty
from app.domain.migrations import MigrationError, MigrationResult
from app.domain.project import LoadedProject, load_project_document

ARCHIVE_FORMAT: Literal["rigstory-archive"] = "rigstory-archive"
ARCHIVE_VERSION = "1.0.0"
MANIFEST_NAME = "manifest.json"
PROJECT_DOCUMENT_NAME = "project.json"

MAX_ARCHIVE_ENTRIES = 4096
MAX_ARCHIVE_TOTAL_BYTES = 128 * 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ASSET_ENTRY_RE = re.compile(r"^assets/sha256/([0-9a-f]{2})/([0-9a-f]{2})/([0-9a-f]{64})$")


class ArchiveError(Exception):
    """A malformed, unsafe, or inconsistent archive."""


class ArchiveConflictError(ArchiveError):
    """The archive's project already exists and the strategy forbids renaming."""


class ArchiveDocumentEntry(BaseModel):
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_length: int = Field(ge=0)

    model_config = ConfigDict(frozen=True, extra="forbid")


class ArchiveAssetEntry(BaseModel):
    id: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    media_type: str
    path: str
    included: bool

    model_config = ConfigDict(frozen=True, extra="forbid")


class ArchiveManifest(BaseModel):
    format: Literal["rigstory-archive"]
    archive_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    schema_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    engine_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    project_id: str
    project_name: str
    created_at: str
    documents: tuple[ArchiveDocumentEntry, ...]
    assets: tuple[ArchiveAssetEntry, ...] = ()

    model_config = ConfigDict(frozen=True, extra="forbid")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def asset_archive_path(sha256: str) -> str:
    """Content-addressed archive entry name for an asset payload."""
    if _SHA256_RE.fullmatch(sha256) is None:
        raise ArchiveError(f"invalid asset sha256: {sha256!r}")
    return f"assets/sha256/{sha256[:2]}/{sha256[2:4]}/{sha256}"


def asset_disk_path(assets_root: Path, sha256: str) -> Path:
    """Content-addressed on-disk location for an asset payload."""
    if _SHA256_RE.fullmatch(sha256) is None:
        raise ArchiveError(f"invalid asset sha256: {sha256!r}")
    return assets_root / "assets" / "sha256" / sha256[:2] / sha256[2:4] / sha256


def build_project_archive(
    document_json: dict[str, JsonValue],
    *,
    assets_root: Path | None = None,
    created_at: str | None = None,
) -> bytes:
    """Build a portable archive from an already-validated project document dump."""
    loaded = load_project_document(dict(document_json))
    document = loaded.document
    document_text = canonical_json_pretty(document.model_dump(mode="json"))
    document_bytes = document_text.encode("utf-8")

    asset_entries: list[ArchiveAssetEntry] = []
    asset_payloads: dict[str, bytes] = {}
    for entry in document.asset_manifest:
        payload: bytes | None = None
        if assets_root is not None:
            disk_path = asset_disk_path(assets_root, entry.sha256)
            if disk_path.is_file():
                payload = disk_path.read_bytes()
                if sha256_hex(payload) != entry.sha256:
                    raise ArchiveError(f"asset {entry.id!r} on disk does not match manifest sha256")
        archive_path = asset_archive_path(entry.sha256)
        if payload is not None:
            asset_payloads[archive_path] = payload
        asset_entries.append(
            ArchiveAssetEntry(
                id=entry.id,
                sha256=entry.sha256,
                media_type=entry.media_type,
                path=archive_path,
                included=payload is not None,
            )
        )

    manifest = ArchiveManifest(
        format=ARCHIVE_FORMAT,
        archive_version=ARCHIVE_VERSION,
        schema_version=document.schema_version,
        engine_version=document.engine_version,
        project_id=document.project.id,
        project_name=document.project.name,
        created_at=created_at or datetime.now(UTC).isoformat(timespec="seconds"),
        documents=(
            ArchiveDocumentEntry(
                path=PROJECT_DOCUMENT_NAME,
                sha256=sha256_hex(document_bytes),
                byte_length=len(document_bytes),
            ),
        ),
        assets=tuple(asset_entries),
    )
    manifest_text = canonical_json_pretty(manifest.model_dump(mode="json"))

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(MANIFEST_NAME, manifest_text)
        archive.writestr(PROJECT_DOCUMENT_NAME, document_bytes)
        for path in sorted(asset_payloads):
            archive.writestr(path, asset_payloads[path])
    return buffer.getvalue()


def _validate_entry_name(name: str) -> None:
    """Reject any entry name that could escape a target directory."""
    if not name or name != name.strip():
        raise ArchiveError(f"archive entry has an unsafe name: {name!r}")
    if "\\" in name or name.startswith("/") or ":" in name:
        raise ArchiveError(f"archive entry has an unsafe name: {name!r}")
    parts = name.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ArchiveError(f"archive entry has an unsafe name: {name!r}")
    if name in (MANIFEST_NAME, PROJECT_DOCUMENT_NAME):
        return
    if _ASSET_ENTRY_RE.fullmatch(name) is None:
        raise ArchiveError(f"archive entry is not part of the format: {name!r}")


@dataclass(frozen=True, slots=True)
class ReadArchive:
    manifest: ArchiveManifest
    raw_document: dict[str, JsonValue]
    assets: dict[str, bytes] = field(default_factory=dict)
    """Included asset payloads keyed by sha256."""


def read_project_archive(data: bytes) -> ReadArchive:
    """Safely open an untrusted archive and verify every checksum.

    The document is returned raw (pre-migration) so the caller can migrate and
    report applied steps.
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ArchiveError("file is not a valid archive") from exc

    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_ARCHIVE_ENTRIES:
            raise ArchiveError(f"archive has more than {MAX_ARCHIVE_ENTRIES} entries")
        total_size = sum(info.file_size for info in infos)
        if total_size > MAX_ARCHIVE_TOTAL_BYTES:
            raise ArchiveError("archive uncompressed size exceeds the import limit")
        names = [info.filename for info in infos if not info.is_dir()]
        for name in names:
            _validate_entry_name(name)
        if MANIFEST_NAME not in names:
            raise ArchiveError("archive has no manifest.json")

        manifest_info = archive.getinfo(MANIFEST_NAME)
        if manifest_info.file_size > MAX_MANIFEST_BYTES:
            raise ArchiveError("archive manifest exceeds the size limit")
        try:
            manifest_raw = json.loads(archive.read(MANIFEST_NAME).decode("utf-8"))
            manifest = ArchiveManifest.model_validate(manifest_raw)
        except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
            raise ArchiveError(f"archive manifest is invalid: {exc}") from exc

        if manifest.archive_version.split(".")[0] != ARCHIVE_VERSION.split(".")[0]:
            raise ArchiveError(
                f"archive version {manifest.archive_version} is not supported "
                f"(current {ARCHIVE_VERSION})"
            )

        document_entry = next(
            (entry for entry in manifest.documents if entry.path == PROJECT_DOCUMENT_NAME),
            None,
        )
        if document_entry is None:
            raise ArchiveError("archive manifest does not list project.json")
        if PROJECT_DOCUMENT_NAME not in names:
            raise ArchiveError("archive has no project.json")

        document_bytes = archive.read(PROJECT_DOCUMENT_NAME)
        if len(document_bytes) != document_entry.byte_length:
            raise ArchiveError("project.json length does not match the manifest")
        if sha256_hex(document_bytes) != document_entry.sha256:
            raise ArchiveError("project.json checksum does not match the manifest")
        try:
            raw_document = json.loads(document_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ArchiveError("project.json is not valid JSON") from exc
        if not isinstance(raw_document, dict):
            raise ArchiveError("project.json must contain a JSON object")

        expected_asset_paths = {entry.path: entry for entry in manifest.assets if entry.included}
        asset_payloads: dict[str, bytes] = {}
        for name in names:
            if name in (MANIFEST_NAME, PROJECT_DOCUMENT_NAME):
                continue
            entry = expected_asset_paths.pop(name, None)
            if entry is None:
                raise ArchiveError(f"archive contains a file the manifest does not list: {name!r}")
            payload = archive.read(name)
            if sha256_hex(payload) != entry.sha256:
                raise ArchiveError(f"asset {entry.id!r} checksum does not match the manifest")
            asset_payloads[entry.sha256] = payload
        if expected_asset_paths:
            missing = ", ".join(sorted(entry.id for entry in expected_asset_paths.values()))
            raise ArchiveError(f"archive manifest lists missing asset files: {missing}")

    return ReadArchive(manifest=manifest, raw_document=raw_document, assets=asset_payloads)


type ConflictStrategy = Literal["new_id", "fail"]


@dataclass(frozen=True, slots=True)
class ImportedProjectArchive:
    loaded: LoadedProject
    manifest: ArchiveManifest
    migration: MigrationResult
    original_project_id: str
    id_reassigned: bool
    warnings: tuple[str, ...]
    assets: dict[str, bytes]


def load_archive_for_import(
    data: bytes,
    *,
    existing_project_ids: frozenset[str],
    on_conflict: ConflictStrategy = "new_id",
    new_project_id: str | None = None,
) -> ImportedProjectArchive:
    """Read, verify, migrate, and conflict-resolve an archive for import.

    Raises :class:`ArchiveError` for unsafe or inconsistent archives and
    ``MigrationError``/``DomainValidationError`` for unmigratable or invalid
    documents. Persistence is left to the caller so the write stays inside the
    project store's transactional revision flow.
    """
    read = read_project_archive(data)
    try:
        loaded = load_project_document(dict(read.raw_document))
    except MigrationError as exc:
        raise ArchiveError(f"archive document cannot be migrated: {exc}") from exc

    original_project_id = loaded.document.project.id
    id_reassigned = False
    if original_project_id in existing_project_ids:
        if on_conflict == "fail":
            raise ArchiveConflictError(
                f"project {original_project_id!r} already exists in this workspace"
            )
        if new_project_id is None:
            raise ArchiveError("a replacement project id is required to resolve the conflict")
        document = loaded.document.model_copy(
            update={"project": loaded.document.project.model_copy(update={"id": new_project_id})}
        )
        loaded = LoadedProject(document=document, migration=loaded.migration)
        id_reassigned = True

    warnings = [
        f"asset {entry.id!r} was not included in the archive and must be re-imported"
        for entry in read.manifest.assets
        if not entry.included
    ]
    return ImportedProjectArchive(
        loaded=loaded,
        manifest=read.manifest,
        migration=loaded.migration,
        original_project_id=original_project_id,
        id_reassigned=id_reassigned,
        warnings=tuple(warnings),
        assets=read.assets,
    )


def write_imported_assets(assets_root: Path, assets: dict[str, bytes]) -> list[str]:
    """Persist verified asset payloads into the content-addressed store."""
    written: list[str] = []
    for sha256, payload in sorted(assets.items()):
        target = asset_disk_path(assets_root, sha256)
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(f".{target.name}.tmp")
        temp.write_bytes(payload)
        temp.replace(target)
        written.append(sha256)
    return written
