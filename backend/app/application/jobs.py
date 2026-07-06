"""In-memory async job orchestration (specs §23.6, plan.md §5.4).

Long-running work (currently only character generation) runs as a job with an
explicit state machine, progress events, and cooperative cancellation. Jobs are
process-local: this is a single-user local-first app, so job history does not
need to survive a restart. Persisting jobs to the database is deferred.

A job body is an async callable receiving a :class:`JobContext` for reporting
progress and observing cancellation, and returning a Pydantic result model. A
raised :class:`JobFailure` carries a machine-readable ``kind`` and ``retryable``
flag so the API can classify timeout-versus-invalid failures.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.canonical import JsonValue
from app.domain.ids import JobId, new_job_id

type JobState = Literal["queued", "running", "succeeded", "failed", "cancelled"]

_TERMINAL_STATES: frozenset[str] = frozenset({"succeeded", "failed", "cancelled"})


class JobFailure(Exception):
    """A job failure with a machine-readable classification."""

    def __init__(
        self,
        message: str,
        *,
        kind: str,
        retryable: bool = False,
        detail: dict[str, JsonValue] | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.retryable = retryable
        self.detail = detail


class JobProgress(BaseModel):
    at: str
    stage: str
    message: str
    fraction: float | None = Field(default=None, ge=0.0, le=1.0)

    model_config = ConfigDict(frozen=True)


class Job(BaseModel):
    """Public, serializable snapshot of a job."""

    id: JobId
    kind: str
    state: JobState
    created_at: str
    updated_at: str
    progress: tuple[JobProgress, ...] = ()
    result: JsonValue | None = None
    error: str | None = None
    error_kind: str | None = None
    retryable: bool = False
    error_detail: dict[str, JsonValue] | None = None

    model_config = ConfigDict(frozen=True)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class _JobEntry:
    def __init__(self, job_id: str, kind: str) -> None:
        self.id = job_id
        self.kind = kind
        self.state: JobState = "queued"
        self.created_at = _now()
        self.updated_at = self.created_at
        self.progress: list[JobProgress] = []
        self.result: JsonValue | None = None
        self.error: str | None = None
        self.error_kind: str | None = None
        self.retryable = False
        self.error_detail: dict[str, JsonValue] | None = None
        self.task: asyncio.Task[None] | None = None
        self.updated = asyncio.Event()

    def _touch(self) -> None:
        self.updated_at = _now()
        self.updated.set()

    def add_progress(self, stage: str, message: str, fraction: float | None) -> None:
        self.progress.append(
            JobProgress(at=_now(), stage=stage, message=message, fraction=fraction)
        )
        self._touch()

    def mark_running(self) -> None:
        self.state = "running"
        self._touch()

    def succeed(self, result: JsonValue) -> None:
        self.state = "succeeded"
        self.result = result
        self._touch()

    def fail(
        self,
        error: str,
        kind: str,
        retryable: bool,
        detail: dict[str, JsonValue] | None,
    ) -> None:
        self.state = "failed"
        self.error = error
        self.error_kind = kind
        self.retryable = retryable
        self.error_detail = detail
        self._touch()

    def cancel(self) -> None:
        self.state = "cancelled"
        self.error = "Job cancelled."
        self.error_kind = "cancelled"
        self._touch()

    def snapshot(self) -> Job:
        return Job(
            id=self.id,
            kind=self.kind,
            state=self.state,
            created_at=self.created_at,
            updated_at=self.updated_at,
            progress=tuple(self.progress),
            result=self.result,
            error=self.error,
            error_kind=self.error_kind,
            retryable=self.retryable,
            error_detail=self.error_detail,
        )


class JobContext:
    """Handle passed to a job body for progress reporting and cancellation."""

    def __init__(self, entry: _JobEntry) -> None:
        self._entry = entry

    async def progress(self, stage: str, message: str, fraction: float | None = None) -> None:
        self._entry.add_progress(stage, message, fraction)
        # Yield control so cancellation and SSE consumers can observe the update.
        await asyncio.sleep(0)


type JobBody = Callable[[JobContext], Awaitable[BaseModel]]


class JobRunner:
    """Schedules job bodies as asyncio tasks."""

    def __init__(self) -> None:
        self._entries: dict[str, _JobEntry] = {}

    def get(self, job_id: str) -> Job | None:
        entry = self._entries.get(job_id)
        return entry.snapshot() if entry is not None else None

    def list_jobs(self) -> list[Job]:
        return [entry.snapshot() for entry in self._entries.values()]

    async def submit(self, *, kind: str, body: JobBody) -> Job:
        entry = _JobEntry(new_job_id(), kind)
        self._entries[entry.id] = entry
        entry.task = asyncio.create_task(self._run(entry, body))
        return entry.snapshot()

    async def _run(self, entry: _JobEntry, body: JobBody) -> None:
        entry.mark_running()
        try:
            result = await body(JobContext(entry))
            entry.succeed(result.model_dump(mode="json"))
        except asyncio.CancelledError:
            entry.cancel()
        except JobFailure as failure:
            entry.fail(str(failure), failure.kind, failure.retryable, failure.detail)
        except Exception as exc:
            entry.fail(str(exc), "internal", False, None)

    async def cancel(self, job_id: str) -> Job | None:
        entry = self._entries.get(job_id)
        if entry is None:
            return None
        if entry.task is not None and not entry.task.done():
            entry.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await entry.task
        elif entry.state not in _TERMINAL_STATES:
            entry.cancel()
        return entry.snapshot()

    async def events(self, job_id: str) -> AsyncIterator[JobProgress]:
        entry = self._entries.get(job_id)
        if entry is None:
            return
        index = 0
        while True:
            while index < len(entry.progress):
                yield entry.progress[index]
                index += 1
            if entry.state in _TERMINAL_STATES:
                return
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(entry.updated.wait(), timeout=0.25)
            entry.updated.clear()


class InlineJobRunner(JobRunner):
    """Runs job bodies to completion synchronously; used by tests for determinism."""

    async def submit(self, *, kind: str, body: JobBody) -> Job:
        entry = _JobEntry(new_job_id(), kind)
        self._entries[entry.id] = entry
        entry.mark_running()
        try:
            result = await body(JobContext(entry))
            entry.succeed(result.model_dump(mode="json"))
        except asyncio.CancelledError:
            entry.cancel()
        except JobFailure as failure:
            entry.fail(str(failure), failure.kind, failure.retryable, failure.detail)
        except Exception as exc:
            entry.fail(str(exc), "internal", False, None)
        return entry.snapshot()
