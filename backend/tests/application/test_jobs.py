from __future__ import annotations

import asyncio

from pydantic import BaseModel

from app.application.jobs import JobContext, JobFailure, JobRunner


class _Result(BaseModel):
    value: int


async def _wait_until(predicate: object, runner: JobRunner, job_id: str) -> None:
    for _ in range(200):
        job = runner.get(job_id)
        if job is not None and callable(predicate) and predicate(job):
            return
        await asyncio.sleep(0.01)
    raise AssertionError("job did not reach the expected state in time")


async def test_successful_job_reports_progress_and_result() -> None:
    runner = JobRunner()

    async def body(ctx: JobContext) -> _Result:
        await ctx.progress("step", "working", 0.5)
        return _Result(value=42)

    submitted = await runner.submit(kind="test", body=body)
    await _wait_until(lambda job: job.state == "succeeded", runner, submitted.id)

    job = runner.get(submitted.id)
    assert job is not None
    assert job.state == "succeeded"
    assert job.result == {"value": 42}
    assert [event.stage for event in job.progress] == ["step"]


async def test_job_failure_carries_classification() -> None:
    runner = JobRunner()

    async def body(ctx: JobContext) -> _Result:
        raise JobFailure("nope", kind="timeout", retryable=True, detail={"reason": "slow"})

    submitted = await runner.submit(kind="test", body=body)
    await _wait_until(lambda job: job.state == "failed", runner, submitted.id)

    job = runner.get(submitted.id)
    assert job is not None
    assert job.error_kind == "timeout"
    assert job.retryable is True
    assert job.error_detail == {"reason": "slow"}


async def test_unexpected_error_becomes_internal_failure() -> None:
    runner = JobRunner()

    async def body(ctx: JobContext) -> _Result:
        raise RuntimeError("kaboom")

    submitted = await runner.submit(kind="test", body=body)
    await _wait_until(lambda job: job.state == "failed", runner, submitted.id)

    job = runner.get(submitted.id)
    assert job is not None
    assert job.error_kind == "internal"
    assert job.retryable is False


async def test_job_can_be_cancelled() -> None:
    runner = JobRunner()
    gate = asyncio.Event()

    async def body(ctx: JobContext) -> _Result:
        await ctx.progress("waiting", "blocked", None)
        await gate.wait()
        return _Result(value=1)

    submitted = await runner.submit(kind="test", body=body)
    await _wait_until(lambda job: job.state == "running", runner, submitted.id)

    cancelled = await runner.cancel(submitted.id)
    assert cancelled is not None
    assert cancelled.state == "cancelled"


async def test_cancel_unknown_job_returns_none() -> None:
    runner = JobRunner()
    assert await runner.cancel("job_missing") is None
    assert runner.get("job_missing") is None


async def test_events_replays_progress_then_terminates() -> None:
    runner = JobRunner()

    async def body(ctx: JobContext) -> _Result:
        await ctx.progress("a", "first", 0.3)
        await ctx.progress("b", "second", 0.6)
        return _Result(value=7)

    submitted = await runner.submit(kind="test", body=body)
    stages = [event.stage async for event in runner.events(submitted.id)]
    assert stages == ["a", "b"]
    assert runner.get(submitted.id).state == "succeeded"  # type: ignore[union-attr]
