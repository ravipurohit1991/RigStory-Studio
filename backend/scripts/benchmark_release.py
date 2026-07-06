from __future__ import annotations

import asyncio
import json
import statistics
import tempfile
from pathlib import Path
from time import perf_counter

from app.domain.canonical import JsonValue
from app.domain.motion import MotionAction, compile_motion_actions
from app.domain.project import ProjectDocument, load_project_document
from app.schemas.exports import MediaExportFormat, MediaExportRequest
from app.services.media_export import MediaExporter

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_sample(relative_path: str) -> dict[str, JsonValue]:
    raw = json.loads((REPO_ROOT / "samples" / relative_path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{relative_path} must contain a JSON object")
    return raw


class _SilentProgress:
    async def progress(self, stage: str, message: str, fraction: float | None = None) -> None:
        await asyncio.sleep(0)


def _median_ms(samples: list[float]) -> float:
    return round(statistics.median(samples) * 1000.0, 3)


def _load_benchmark(raw: dict[str, JsonValue], repeats: int) -> dict[str, float | int]:
    samples: list[float] = []
    for _ in range(repeats):
        started = perf_counter()
        load_project_document(raw)
        samples.append(perf_counter() - started)
    return {"repeats": repeats, "median_ms": _median_ms(samples)}


def _compile_benchmark(document: ProjectDocument, repeats: int) -> dict[str, float | int]:
    scene = next(candidate for candidate in document.scenes if candidate.actors)
    actor = scene.actors[0]
    character = next(
        candidate for candidate in document.characters if candidate.id == actor.character_id
    )
    actions = (
        MotionAction(id="action_walk", type="locomote", duration=1.1, target=(1.2, 0.0)),
        MotionAction(id="action_wave", type="wave", duration=1.0, repetitions=2),
    )
    samples: list[float] = []
    for index in range(repeats):
        started = perf_counter()
        compile_motion_actions(
            scene=scene,
            actor_id=actor.id,
            character=character,
            actions=actions,
            clip_id=f"clip_benchmark_{index}",
        )
        samples.append(perf_counter() - started)
    return {"repeats": repeats, "median_ms": _median_ms(samples)}


async def _export_benchmark(
    document: ProjectDocument,
    *,
    format_name: MediaExportFormat,
    frame_rate: int,
    width: int,
    height: int,
) -> dict[str, float | int | str]:
    clip = document.clips[0]
    with tempfile.TemporaryDirectory() as temp:
        exporter = MediaExporter(Path(temp))
        started = perf_counter()
        result = await exporter.export_clip(
            document=document,
            clip=clip,
            settings=MediaExportRequest(
                format=format_name,
                frame_rate=frame_rate,
                width=width,
                height=height,
            ),
            progress=_SilentProgress(),
        )
        elapsed = perf_counter() - started
    return {
        "format": format_name,
        "duration_ms": round(elapsed * 1000.0, 3),
        "frame_count": result.frame_count,
        "frame_rate": result.frame_rate,
        "width": result.width,
        "height": result.height,
        "byte_length": result.byte_length,
    }


async def main() -> None:
    raw = _load_sample("projects/biped-demo.rigstory.json")
    document = load_project_document(raw).document
    results: dict[str, object] = {
        "sample": "samples/projects/biped-demo.rigstory.json",
        "project_load": _load_benchmark(raw, repeats=50),
        "motion_compile": _compile_benchmark(document, repeats=25),
        "png_sequence_export": await _export_benchmark(
            document,
            format_name="png_sequence",
            frame_rate=12,
            width=320,
            height=240,
        ),
    }
    try:
        results["webm_export"] = await _export_benchmark(
            document,
            format_name="webm",
            frame_rate=6,
            width=160,
            height=120,
        )
    except Exception as exc:
        results["webm_export"] = {"skipped": type(exc).__name__, "message": str(exc)}

    print(json.dumps(results, indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
