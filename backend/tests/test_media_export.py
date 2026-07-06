from __future__ import annotations

import asyncio
import io
import json
import zipfile
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient
from PIL import Image

from app.domain.project import load_project_document
from app.schemas.exports import MediaExportRequest
from app.services.media_export import MediaExporter
from tests.sample_paths import load_sample


def _create_project(client: TestClient) -> dict[str, Any]:
    response = client.post(
        "/api/v1/projects",
        json={"document": load_sample("projects/biped-demo.rigstory.json")},
    )
    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


def _wait_for_job(client: TestClient, job_id: str) -> dict[str, Any]:
    for _ in range(200):
        response = client.get(f"/api/v1/jobs/{job_id}")
        assert response.status_code == 200
        job = response.json()
        if job["state"] in {"succeeded", "failed", "cancelled"}:
            return cast(dict[str, Any], job)
    raise AssertionError("job did not finish")


def test_png_sequence_export_reports_progress_and_downloads_zip(client: TestClient) -> None:
    _create_project(client)
    submitted = client.post(
        "/api/v1/clips/clip_wave/export",
        json={
            "format": "png_sequence",
            "frame_rate": 4,
            "width": 160,
            "height": 120,
            "background": "#ffffff",
            "transparent": False,
        },
    )
    assert submitted.status_code == 202

    job = _wait_for_job(client, submitted.json()["id"])
    assert job["state"] == "succeeded"
    result = job["result"]
    assert result["format"] == "png_sequence"
    assert result["frame_rate"] == 4
    assert result["frame_count"] == 5
    assert result["duration"] == 1.2
    assert [event["stage"] for event in job["progress"]] == [
        "prepare",
        "render",
        "package",
        "complete",
    ]

    download = client.get(result["download_url"])
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
        frame_names = sorted(name for name in archive.namelist() if name.startswith("frames/"))
        assert len(frame_names) == result["frame_count"]
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["width"] == 160
        assert manifest["height"] == 120
        image = Image.open(io.BytesIO(archive.read(frame_names[0])))
        assert image.size == (160, 120)
        assert image.mode == "RGBA"


def test_webm_export_encodes_downloadable_video(client: TestClient) -> None:
    _create_project(client)
    submitted = client.post(
        "/api/v1/clips/clip_wave/export",
        json={"format": "webm", "frame_rate": 2, "width": 96, "height": 72},
    )
    assert submitted.status_code == 202

    job = _wait_for_job(client, submitted.json()["id"])
    assert job["state"] == "succeeded", job
    result = job["result"]
    assert result["format"] == "webm"
    assert result["media_type"] == "video/webm"
    assert result["frame_count"] == 3

    download = client.get(result["download_url"])
    assert download.status_code == 200
    assert download.headers["content-type"] == "video/webm"
    assert download.content[:4] == bytes.fromhex("1a45dfa3")


class _CancellingProgress:
    def __init__(self) -> None:
        self.calls = 0

    async def progress(self, stage: str, message: str, fraction: float | None = None) -> None:
        self.calls += 1
        if self.calls >= 2:
            raise asyncio.CancelledError


async def test_cancelled_media_export_removes_temporary_artifacts(tmp_path: Path) -> None:
    document = load_sample("projects/biped-demo.rigstory.json")
    exporter = MediaExporter(tmp_path)
    loaded = load_project_document(document).document
    parsed_clip = next(candidate for candidate in loaded.clips if candidate.id == "clip_wave")

    try:
        await exporter.export_clip(
            document=loaded,
            clip=parsed_clip,
            settings=MediaExportRequest(format="png_sequence", frame_rate=4, width=64, height=64),
            progress=_CancellingProgress(),
        )
    except asyncio.CancelledError:
        pass
    else:
        raise AssertionError("export did not cancel")

    exports_root = tmp_path / "exports"
    assert not exports_root.exists() or list(exports_root.iterdir()) == []
