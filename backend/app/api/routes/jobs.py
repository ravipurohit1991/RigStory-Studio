from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.api.deps import get_job_runner
from app.application.jobs import Job, JobRunner

router = APIRouter(tags=["jobs"])
JobRunnerDep = Annotated[JobRunner, Depends(get_job_runner)]


@router.get("/jobs/{job_id}", response_model=Job)
def get_job(job_id: str, runner: JobRunnerDep) -> Job:
    job = runner.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    return job


@router.post("/jobs/{job_id}/cancel", response_model=Job)
async def cancel_job(job_id: str, runner: JobRunnerDep) -> Job:
    job = await runner.cancel(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    return job


@router.get("/jobs/{job_id}/events")
async def job_events(job_id: str, runner: JobRunnerDep) -> StreamingResponse:
    if runner.get(job_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")

    async def stream() -> AsyncIterator[str]:
        async for progress in runner.events(job_id):
            yield f"event: progress\ndata: {progress.model_dump_json()}\n\n"
        final = runner.get(job_id)
        if final is not None:
            yield f"event: state\ndata: {final.model_dump_json()}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
