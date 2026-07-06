from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.routes.projects import MAX_PROJECT_ARCHIVE_BYTES
from app.domain.canonical import canonical_json_pretty
from app.services.project_archive import (
    ARCHIVE_FORMAT,
    ARCHIVE_VERSION,
    MANIFEST_NAME,
    PROJECT_DOCUMENT_NAME,
    ArchiveError,
    asset_disk_path,
    build_project_archive,
    read_project_archive,
    sha256_hex,
)
from app.services.project_store import FileProjectStore
from tests.sample_paths import load_sample


def _create_project(
    client: TestClient, sample: str = "projects/biped-demo.rigstory.json"
) -> dict[str, Any]:
    raw = load_sample(sample)
    response = client.post("/api/v1/projects", json={"document": raw})
    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


def _export_archive(client: TestClient, project_id: str) -> bytes:
    response = client.get(f"/api/v1/projects/{project_id}/export")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "attachment" in response.headers["content-disposition"]
    content: object = response.content
    assert isinstance(content, bytes)
    return content


def _import_archive(client: TestClient, payload: bytes, **params: str) -> httpx.Response:
    response: object = client.post(
        "/api/v1/projects/import",
        params=params,
        content=payload,
        headers={"Content-Type": "application/zip"},
    )
    assert isinstance(response, httpx.Response)
    return response


def test_archive_export_import_round_trip_assigns_new_id_on_conflict(
    client: TestClient,
) -> None:
    created = _create_project(client)
    project_id = created["document"]["project"]["id"]
    payload = _export_archive(client, project_id)

    response = _import_archive(client, payload)
    assert response.status_code == 201
    imported = response.json()
    assert imported["original_project_id"] == project_id
    assert imported["id_reassigned"] is True
    assert imported["document"]["project"]["id"] != project_id
    assert imported["migration"]["applied"] == []
    # Everything except the reassigned project id survives the round trip.
    original = dict(created["document"])
    round_tripped = dict(imported["document"])
    original.pop("project")
    round_tripped.pop("project")
    assert round_tripped == original


def test_archive_import_conflict_fail_strategy_returns_409(client: TestClient) -> None:
    created = _create_project(client)
    project_id = created["document"]["project"]["id"]
    payload = _export_archive(client, project_id)

    response = _import_archive(client, payload, on_conflict="fail")
    assert response.status_code == 409


def test_archive_import_into_clean_workspace_keeps_original_id(client: TestClient) -> None:
    created = _create_project(client)
    project_id = created["document"]["project"]["id"]
    payload = _export_archive(client, project_id)

    assert client.delete(f"/api/v1/projects/{project_id}").status_code == 204

    response = _import_archive(client, payload)
    assert response.status_code == 201
    imported = response.json()
    assert imported["id_reassigned"] is False
    assert imported["document"]["project"]["id"] == project_id


def _rewrite_entry(payload: bytes, name: str, data: bytes) -> bytes:
    """Rebuild a zip with one entry replaced (or added)."""
    source = zipfile.ZipFile(io.BytesIO(payload))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as target:
        replaced = False
        for info in source.infolist():
            if info.filename == name:
                target.writestr(name, data)
                replaced = True
            else:
                target.writestr(info.filename, source.read(info.filename))
        if not replaced:
            target.writestr(name, data)
    return buffer.getvalue()


def test_tampered_document_checksum_is_rejected(client: TestClient) -> None:
    created = _create_project(client)
    project_id = created["document"]["project"]["id"]
    payload = _export_archive(client, project_id)

    document = json.loads(zipfile.ZipFile(io.BytesIO(payload)).read(PROJECT_DOCUMENT_NAME))
    document["project"]["name"] = "Tampered Name"
    tampered_bytes = canonical_json_pretty(document).encode("utf-8")
    tampered = _rewrite_entry(payload, PROJECT_DOCUMENT_NAME, tampered_bytes)

    response = _import_archive(client, tampered)
    assert response.status_code == 422
    assert "checksum" in response.json()["detail"] or "length" in response.json()["detail"]


def test_unlisted_archive_entry_is_rejected(client: TestClient) -> None:
    created = _create_project(client)
    project_id = created["document"]["project"]["id"]
    payload = _export_archive(client, project_id)

    with_extra = _rewrite_entry(payload, "assets/sha256/aa/bb/" + "a" * 64, b"sneaky")
    response = _import_archive(client, with_extra)
    assert response.status_code == 422


@pytest.mark.parametrize(
    "entry_name",
    [
        "../escape.json",
        "/absolute.json",
        "assets/../../escape.json",
        "c:/windows/escape.json",
        "assets\\sha256\\escape.json",
    ],
)
def test_unsafe_entry_names_are_rejected(entry_name: str) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(MANIFEST_NAME, "{}")
        archive.writestr(entry_name, b"payload")

    with pytest.raises(ArchiveError, match=r"unsafe|not part of the format"):
        read_project_archive(buffer.getvalue())


def test_non_zip_payload_is_rejected(client: TestClient) -> None:
    response = _import_archive(client, b"this is not a zip archive")
    assert response.status_code == 422

    empty = client.post("/api/v1/projects/import")
    assert empty.status_code == 422


def test_archive_import_rejects_oversized_body(client: TestClient) -> None:
    response = _import_archive(client, b"x" * (MAX_PROJECT_ARCHIVE_BYTES + 1))

    assert response.status_code == 413
    assert "byte limit" in response.json()["detail"]


def _archive_for_document(raw_document: dict[str, Any]) -> bytes:
    """Build an archive by hand so older schema versions can be simulated."""
    document_bytes = canonical_json_pretty(raw_document).encode("utf-8")
    manifest = {
        "format": ARCHIVE_FORMAT,
        "archive_version": ARCHIVE_VERSION,
        "schema_version": raw_document["schema_version"],
        "engine_version": raw_document["engine_version"],
        "project_id": raw_document["project"]["id"],
        "project_name": raw_document["project"]["name"],
        "created_at": "2026-07-05T00:00:00+00:00",
        "documents": [
            {
                "path": PROJECT_DOCUMENT_NAME,
                "sha256": sha256_hex(document_bytes),
                "byte_length": len(document_bytes),
            }
        ],
        "assets": [],
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(MANIFEST_NAME, canonical_json_pretty(manifest))
        archive.writestr(PROJECT_DOCUMENT_NAME, document_bytes)
    return buffer.getvalue()


def test_import_migrates_older_archive_and_reports_steps(client: TestClient) -> None:
    raw = load_sample("migrations/walker-project-0.3.0.rigstory.json")
    payload = _archive_for_document(raw)

    response = _import_archive(client, payload)
    assert response.status_code == 201
    imported = response.json()
    assert imported["migration"]["from_version"] == "0.3.0"
    assert imported["migration"]["to_version"] == imported["document"]["schema_version"]
    assert imported["migration"]["applied"][0] == "0.3.0->0.4.0"
    # The 0.3.0 -> 0.4.0 step derives walkability for old floor objects.
    floor = imported["document"]["scenes"][0]["objects"][0]
    assert floor["walkable"] is True
    assert floor["visual"]["type"] == "rectangle"


def test_asset_payloads_round_trip_content_addressed(tmp_path: Path) -> None:
    store = FileProjectStore(tmp_path)
    raw = load_sample("projects/biped-demo.rigstory.json")
    asset_payload = b"<svg xmlns='http://www.w3.org/2000/svg'/>"
    digest = sha256_hex(asset_payload)
    raw["asset_manifest"] = [
        {
            "id": "asset_walker_texture",
            "sha256": digest,
            "media_type": "image/svg+xml",
            "display_name": "Walker texture",
        }
    ]
    disk_path = asset_disk_path(tmp_path, digest)
    disk_path.parent.mkdir(parents=True, exist_ok=True)
    disk_path.write_bytes(asset_payload)

    payload = build_project_archive(raw, assets_root=tmp_path)
    read = read_project_archive(payload)
    assert read.manifest.assets[0].included is True
    assert read.assets[digest] == asset_payload

    # A manifest entry without a payload on disk is exported as not included
    # and reported as a warning on import rather than failing.
    disk_path.unlink()
    partial = build_project_archive(raw, assets_root=tmp_path)
    partial_read = read_project_archive(partial)
    assert partial_read.manifest.assets[0].included is False
    assert partial_read.assets == {}
    assert store.project_ids() == frozenset()
