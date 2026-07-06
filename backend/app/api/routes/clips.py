from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from app.api.deps import get_job_runner, get_project_store
from app.application.jobs import Job, JobContext, JobRunner
from app.schemas.exports import MediaExportRead, MediaExportRequest
from app.services.media_export import MediaExporter, MediaExportError, export_path_for_download
from app.services.project_store import FileProjectStore, ProjectNotFoundError

router = APIRouter(tags=["clips", "exports"])
ProjectStoreDep = Annotated[FileProjectStore, Depends(get_project_store)]
JobRunnerDep = Annotated[JobRunner, Depends(get_job_runner)]


@router.post(
    "/clips/{clip_id}/export",
    response_model=Job,
    status_code=status.HTTP_202_ACCEPTED,
)
async def export_clip_media(
    clip_id: str,
    payload: MediaExportRequest,
    store: ProjectStoreDep,
    runner: JobRunnerDep,
) -> Job:
    try:
        stored = store.get_clip(clip_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="clip not found") from exc

    exporter = MediaExporter(store.base_path)

    async def body(progress: JobContext) -> MediaExportRead:
        result = await exporter.export_clip(
            document=stored.document,
            clip=stored.clip,
            settings=payload,
            progress=progress,
        )
        return result

    return await runner.submit(kind="media_export", body=body)


@router.get("/exports/{export_id}/{file_name}")
def download_export(
    export_id: str,
    file_name: str,
    store: ProjectStoreDep,
) -> FileResponse:
    try:
        path = export_path_for_download(store.base_path, export_id, file_name)
    except MediaExportError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    media_type = "application/octet-stream"
    if file_name.endswith(".zip"):
        media_type = "application/zip"
    elif file_name.endswith(".svg"):
        media_type = "image/svg+xml"
    elif file_name.endswith(".webm"):
        media_type = "video/webm"
    return FileResponse(path, media_type=media_type, filename=file_name)
