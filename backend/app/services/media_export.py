"""Media export for native clips.

The exporter renders deterministic frames from the native project document and
writes user-visible artifacts only after the whole export succeeds. Long runs
report progress through the shared job runner and clean up temporary output if
the job is cancelled.
"""

from __future__ import annotations

import asyncio
import base64
import json
import math
import os
import shutil
import uuid
import zipfile
from itertools import pairwise
from pathlib import Path
from typing import Protocol

from PIL import Image, ImageDraw

from app.application.jobs import JobFailure
from app.domain.character import AttachmentDefinition, PrimitiveAttachmentSpec
from app.domain.clip import (
    AnimationClip,
    BoneRotationTrack,
    BoneScaleTrack,
    ConstraintWeightTrack,
    RootTranslationTrack,
    ScalarKeyframe,
    VectorKeyframe,
)
from app.domain.math2d.affine import Affine2
from app.domain.math2d.angles import lerp_angle_deg
from app.domain.math2d.vec2 import Vec2
from app.domain.mesh_skinning import skin_attachment_vertices
from app.domain.project import ProjectDocument
from app.domain.rig import RigDefinition, compute_bone_endpoints, compute_world_transforms
from app.domain.scene import SceneDefinition
from app.schemas.exports import MediaExportRead, MediaExportRequest
from app.services.project_archive import sha256_hex

type Rgba = tuple[int, int, int, int]


class ProgressReporter(Protocol):
    async def progress(self, stage: str, message: str, fraction: float | None = None) -> None: ...


class MediaExportError(Exception):
    pass


def _parse_hex_color(value: str, alpha: float = 1.0) -> Rgba:
    text = value.removeprefix("#")
    return (
        int(text[0:2], 16),
        int(text[2:4], 16),
        int(text[4:6], 16),
        max(0, min(255, round(alpha * 255))),
    )


def _world_to_canvas(
    bounds: tuple[float, float, float, float],
    width: int,
    height: int,
    point: Vec2,
    padding_ratio: float = 0.05,
) -> tuple[float, float]:
    min_x, min_y, max_x, max_y = bounds
    world_width = max(max_x - min_x, 1e-6)
    world_height = max(max_y - min_y, 1e-6)
    padding = min(width, height) * padding_ratio
    scale = min((width - padding * 2) / world_width, (height - padding * 2) / world_height)
    offset_x = (width - world_width * scale) / 2 - min_x * scale
    offset_y = (height - world_height * scale) / 2 + max_y * scale
    return (point.x * scale + offset_x, offset_y - point.y * scale)


def _interpolation_weight(kind: str, t: float) -> float:
    if kind == "stepped":
        return 0.0
    if kind == "cubic":
        return t * t * (3.0 - 2.0 * t)
    return t


def _scalar_value(
    keyframes: tuple[ScalarKeyframe, ...],
    time: float,
    *,
    angle: bool = False,
) -> float | None:
    if not keyframes:
        return None
    ordered = sorted(keyframes, key=lambda key: (key.time, key.id))
    if time <= ordered[0].time:
        return ordered[0].value
    if time >= ordered[-1].time:
        return ordered[-1].value
    for left, right in pairwise(ordered):
        if time < left.time or time > right.time:
            continue
        span = right.time - left.time
        weight = (
            0.0
            if span <= 0.0
            else _interpolation_weight(left.interpolation, (time - left.time) / span)
        )
        if angle:
            return lerp_angle_deg(left.value, right.value, weight)
        return left.value + (right.value - left.value) * weight
    return ordered[0].value


def _vector_value(
    keyframes: tuple[VectorKeyframe, ...],
    time: float,
) -> tuple[float, float] | None:
    if not keyframes:
        return None
    ordered = sorted(keyframes, key=lambda key: (key.time, key.id))
    if time <= ordered[0].time:
        return ordered[0].value
    if time >= ordered[-1].time:
        return ordered[-1].value
    for left, right in pairwise(ordered):
        if time < left.time or time > right.time:
            continue
        span = right.time - left.time
        weight = (
            0.0
            if span <= 0.0
            else _interpolation_weight(left.interpolation, (time - left.time) / span)
        )
        return (
            left.value[0] + (right.value[0] - left.value[0]) * weight,
            left.value[1] + (right.value[1] - left.value[1]) * weight,
        )
    return ordered[0].value


def _wrap_time(clip: AnimationClip, time: float) -> float:
    if not clip.loop:
        return min(max(0.0, time), clip.duration)
    if clip.loop_range is None:
        start = 0.0
        end = clip.duration
    else:
        start = min(max(0.0, clip.loop_range[0]), clip.duration)
        end = min(max(0.0, clip.loop_range[1]), clip.duration)
        if start >= end:
            start = 0.0
            end = clip.duration
    if time < start:
        return start
    if time <= end:
        return time
    span = end - start
    wrapped = math.fmod(time - start, span)
    return start + (wrapped + span if wrapped < 0.0 else wrapped)


class _ActorPose:
    def __init__(self) -> None:
        self.root_translation: tuple[float, float] | None = None
        self.bone_rotations: dict[str, float] = {}
        self.bone_scales: dict[str, tuple[float, float]] = {}


def _evaluate_clip(clip: AnimationClip, time: float) -> dict[str, _ActorPose]:
    sample_time = _wrap_time(clip, time)
    poses: dict[str, _ActorPose] = {}
    for track in clip.tracks:
        actor = poses.setdefault(track.actor_id, _ActorPose())
        if isinstance(track, BoneRotationTrack):
            scalar_value = _scalar_value(track.keyframes, sample_time, angle=True)
            if scalar_value is not None:
                actor.bone_rotations[track.bone_id] = scalar_value
        elif isinstance(track, RootTranslationTrack):
            actor.root_translation = _vector_value(track.keyframes, sample_time)
        elif isinstance(track, BoneScaleTrack):
            vector_value = _vector_value(track.keyframes, sample_time)
            if vector_value is not None:
                actor.bone_scales[track.bone_id] = vector_value
        elif isinstance(track, ConstraintWeightTrack):
            continue
    return poses


def _pose_rig(rig: RigDefinition, pose: _ActorPose | None) -> RigDefinition:
    if pose is None:
        return rig
    bones = []
    for bone in rig.bones:
        rotation = pose.bone_rotations.get(bone.id)
        scale = pose.bone_scales.get(bone.id)
        if rotation is None and scale is None:
            bones.append(bone)
            continue
        bones.append(
            bone.model_copy(
                update={
                    "setup_transform": bone.setup_transform.model_copy(
                        update={
                            "rotation_deg": rotation
                            if rotation is not None
                            else bone.setup_transform.rotation_deg,
                            "scale": scale if scale is not None else bone.setup_transform.scale,
                        }
                    )
                }
            )
        )
    return rig.model_copy(update={"bones": tuple(bones)})


def _primitive_points(
    primitive: PrimitiveAttachmentSpec,
    pivot: tuple[float, float],
) -> list[Vec2]:
    width, height = primitive.size
    left = -pivot[0]
    right = width - pivot[0]
    bottom = -height / 2.0 - pivot[1]
    top = height / 2.0 - pivot[1]
    if primitive.shape == "rectangle":
        return [Vec2(left, bottom), Vec2(right, bottom), Vec2(right, top), Vec2(left, top)]
    if primitive.shape == "ellipse":
        return [
            Vec2(
                left + width / 2.0 + math.cos(math.tau * index / 24.0) * width / 2.0,
                math.sin(math.tau * index / 24.0) * height / 2.0 - pivot[1],
            )
            for index in range(24)
        ]
    radius = height / 2.0
    straight = max(0.0, width - height)
    points: list[Vec2] = []
    for index in range(24):
        if index < 12:
            angle = math.pi / 2.0 - math.pi * index / 11.0
            center_x = left + straight + radius
        else:
            angle = -math.pi / 2.0 - math.pi * (index - 12) / 11.0
            center_x = left + radius
        points.append(
            Vec2(center_x + math.cos(angle) * radius, math.sin(angle) * radius - pivot[1])
        )
    return points


def _fallback_primitive(bone_length: float, attachment_id: str) -> PrimitiveAttachmentSpec:
    if "head" in attachment_id:
        return PrimitiveAttachmentSpec(shape="ellipse", size=(0.42, 0.36), fill="#f0c8a0")
    if "torso" in attachment_id or "pelvis" in attachment_id:
        return PrimitiveAttachmentSpec(
            shape="rectangle",
            size=(0.5, 0.34),
            fill="#6b8fa8",
            opacity=0.92,
        )
    return PrimitiveAttachmentSpec(
        shape="capsule",
        size=(max(0.18, bone_length), 0.16),
        fill="#e6b17a",
    )


def _draw_polygon(
    draw: ImageDraw.ImageDraw,
    points: list[Vec2],
    scene: SceneDefinition,
    width: int,
    height: int,
    fill: Rgba,
) -> None:
    if len(points) < 3:
        return
    draw.polygon(
        [_world_to_canvas(scene.world_bounds, width, height, point) for point in points],
        fill=fill,
    )


def _draw_scene(draw: ImageDraw.ImageDraw, scene: SceneDefinition, width: int, height: int) -> None:
    for scene_object in scene.objects:
        if not scene_object.visible:
            continue
        if scene_object.visual.type == "rectangle":
            min_x, min_y, max_x, max_y = scene_object.bounds
            color = _parse_hex_color(scene_object.visual.fill, scene_object.visual.opacity)
            x1, y1 = _world_to_canvas(scene.world_bounds, width, height, Vec2(min_x, max_y))
            x2, y2 = _world_to_canvas(scene.world_bounds, width, height, Vec2(max_x, min_y))
            draw.rectangle((x1, y1, x2, y2), fill=color)
        elif scene_object.visual.type == "polygon":
            color = _parse_hex_color(scene_object.visual.fill, scene_object.visual.opacity)
            points = [Vec2(x, y) for x, y in scene_object.visual.vertices]
            _draw_polygon(draw, points, scene, width, height, color)


def _draw_attachment(
    draw: ImageDraw.ImageDraw,
    attachment: AttachmentDefinition,
    rig: RigDefinition,
    bone_world: Affine2,
    actor_world: Affine2,
    scene: SceneDefinition,
    width: int,
    height: int,
) -> None:
    attachment_world = actor_world.multiply(
        bone_world.multiply(attachment.transform.to_transform2d().to_affine())
    )
    if attachment.kind == "mesh" and attachment.mesh is not None:
        vertices = skin_attachment_vertices(attachment, rig)
        color = _parse_hex_color(attachment.mesh.fill, attachment.mesh.opacity)
        for triangle in attachment.mesh.triangles:
            points = [attachment_world.apply_point(vertices[index]) for index in triangle.indices]
            _draw_polygon(draw, points, scene, width, height, color)
        return

    bone = next(candidate for candidate in rig.bones if candidate.id == attachment.bone_id)
    primitive = attachment.primitive or _fallback_primitive(bone.length, attachment.id)
    color = _parse_hex_color(primitive.fill, primitive.opacity)
    points = [
        attachment_world.apply_point(point)
        for point in _primitive_points(primitive, attachment.pivot)
    ]
    _draw_polygon(draw, points, scene, width, height, color)


def _render_frame(
    document: ProjectDocument,
    clip: AnimationClip,
    time: float,
    settings: MediaExportRequest,
) -> Image.Image:
    background = (
        (0, 0, 0, 0) if settings.transparent else _parse_hex_color(settings.background or "#ffffff")
    )
    image = Image.new("RGBA", (settings.width, settings.height), background)
    draw = ImageDraw.Draw(image, "RGBA")
    scene = next(candidate for candidate in document.scenes if candidate.id == clip.scene_id)
    characters = {character.id: character for character in document.characters}
    _draw_scene(draw, scene, settings.width, settings.height)
    poses = _evaluate_clip(clip, time)

    for actor in scene.actors:
        character = characters.get(actor.character_id)
        if character is None:
            continue
        pose = poses.get(actor.id)
        root = (
            pose.root_translation
            if pose is not None and pose.root_translation is not None
            else actor.root_transform.position
        )
        actor_world = Affine2.from_trs(
            Vec2(root[0], root[1]),
            actor.root_transform.rotation_deg,
            actor.root_transform.scale,
        )
        rig = _pose_rig(character.rig, pose)
        worlds = compute_world_transforms(rig)
        visible = sorted(
            (attachment for attachment in character.attachments if attachment.visible),
            key=lambda item: (item.z_index, item.id),
        )
        for attachment in visible:
            bone_world = worlds.get(attachment.bone_id)
            if bone_world is None:
                continue
            _draw_attachment(
                draw,
                attachment,
                rig,
                bone_world,
                actor_world,
                scene,
                settings.width,
                settings.height,
            )
        if not visible:
            endpoints = compute_bone_endpoints(rig)
            for origin, tip in endpoints.values():
                start = _world_to_canvas(
                    scene.world_bounds,
                    settings.width,
                    settings.height,
                    actor_world.apply_point(origin),
                )
                end = _world_to_canvas(
                    scene.world_bounds,
                    settings.width,
                    settings.height,
                    actor_world.apply_point(tip),
                )
                draw.line((start, end), fill=(53, 92, 125, 255), width=3)
    return image


def _frame_times(clip: AnimationClip, frame_rate: int) -> list[float]:
    frame_count = max(1, math.ceil(clip.duration * frame_rate))
    return [min(index / frame_rate, clip.duration) for index in range(frame_count)]


def _write_png_sequence(
    document: ProjectDocument,
    clip: AnimationClip,
    settings: MediaExportRequest,
    temp_dir: Path,
) -> list[Path]:
    frame_paths: list[Path] = []
    for index, time in enumerate(_frame_times(clip, settings.frame_rate)):
        frame = _render_frame(document, clip, time, settings)
        path = temp_dir / f"frame_{index:06d}.png"
        frame.save(path)
        frame_paths.append(path)
    return frame_paths


def _zip_png_sequence(
    frame_paths: list[Path],
    clip: AnimationClip,
    settings: MediaExportRequest,
    output_path: Path,
) -> None:
    manifest = {
        "format": "rigstory-png-sequence",
        "clip_id": clip.id,
        "duration": clip.duration,
        "frame_rate": settings.frame_rate,
        "frame_count": len(frame_paths),
        "width": settings.width,
        "height": settings.height,
        "transparent": settings.transparent,
        "background": settings.background,
    }
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, sort_keys=True))
        for path in frame_paths:
            archive.write(path, f"frames/{path.name}")


def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def _animated_svg_from_frames(
    frame_paths: list[Path],
    clip: AnimationClip,
    settings: MediaExportRequest,
) -> str:
    duration = max(clip.duration, 1e-6)
    images: list[str] = []
    frame_duration = 1.0 / settings.frame_rate
    for index, path in enumerate(frame_paths):
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        begin = index * frame_duration
        visible_for = min(frame_duration, max(0.0, duration - begin))
        images.append(
            "<image "
            f'width="{settings.width}" height="{settings.height}" '
            f'href="data:image/png;base64,{encoded}" opacity="0">'
            f'<animate attributeName="opacity" values="0;1;1;0" '
            f'keyTimes="0;0.001;0.999;1" begin="{begin:.6f}s" '
            f'dur="{max(visible_for, 0.001):.6f}s" fill="freeze" />'
            "</image>"
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{settings.width}" '
        f'height="{settings.height}" viewBox="0 0 {settings.width} {settings.height}" '
        f'role="img" aria-label="{_xml_escape(clip.name)}">'
        f"<title>{_xml_escape(clip.name)}</title>"
        f"<desc>RigStory animated SVG export, duration {duration:.3f}s.</desc>"
        + "".join(images)
        + "</svg>"
    )


async def _encode_webm(
    frame_dir: Path,
    output_path: Path,
    settings: MediaExportRequest,
) -> None:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-framerate",
        str(settings.frame_rate),
        "-i",
        str(frame_dir / "frame_%06d.png"),
        "-c:v",
        "libvpx-vp9",
        "-pix_fmt",
        "yuva420p" if settings.transparent else "yuv420p",
        "-auto-alt-ref",
        "0",
        str(output_path),
    ]
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise JobFailure(
            "ffmpeg is required for WebM export but was not found",
            kind="export_encoder_missing",
            retryable=False,
        ) from exc
    try:
        _stdout, stderr = await process.communicate()
    except asyncio.CancelledError:
        process.kill()
        await process.wait()
        raise
    if process.returncode != 0:
        raise JobFailure(
            "WebM export failed",
            kind="export_encoder_failed",
            retryable=False,
            detail={"stderr": stderr.decode("utf-8", errors="replace")[-1000:]},
        )


def _atomic_publish(temp_dir: Path, final_dir: Path) -> None:
    final_dir.parent.mkdir(parents=True, exist_ok=True)
    os.replace(temp_dir, final_dir)


class MediaExporter:
    def __init__(self, asset_store_path: Path) -> None:
        self.exports_root = asset_store_path / "exports"

    async def export_clip(
        self,
        *,
        document: ProjectDocument,
        clip: AnimationClip,
        settings: MediaExportRequest,
        progress: ProgressReporter,
    ) -> MediaExportRead:
        export_id = f"export_{uuid.uuid4().hex}"
        temp_dir = self.exports_root / f".{export_id}.tmp"
        final_dir = self.exports_root / export_id
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        temp_dir.mkdir(parents=True)
        published = False
        try:
            await progress.progress("prepare", "Preparing clip export", 0.05)
            frame_paths = _write_png_sequence(document, clip, settings, temp_dir)
            await progress.progress("render", "Rendered export frames", 0.65)

            if settings.format == "png_sequence":
                file_name = f"{clip.id}-png-sequence.zip"
                media_type = "application/zip"
                output_path = temp_dir / file_name
                _zip_png_sequence(frame_paths, clip, settings, output_path)
            elif settings.format == "animated_svg":
                file_name = f"{clip.id}.svg"
                media_type = "image/svg+xml"
                output_path = temp_dir / file_name
                output_path.write_text(
                    _animated_svg_from_frames(frame_paths, clip, settings),
                    encoding="utf-8",
                )
            else:
                file_name = f"{clip.id}.webm"
                media_type = "video/webm"
                output_path = temp_dir / file_name
                await _encode_webm(temp_dir, output_path, settings)

            await progress.progress("package", "Packaged export artifact", 0.9)
            payload = output_path.read_bytes()
            result = MediaExportRead(
                export_id=export_id,
                clip_id=clip.id,
                format=settings.format,
                file_name=file_name,
                media_type=media_type,
                download_url=f"/api/v1/exports/{export_id}/{file_name}",
                byte_length=len(payload),
                sha256=sha256_hex(payload),
                duration=clip.duration,
                frame_rate=settings.frame_rate,
                frame_count=len(frame_paths),
                width=settings.width,
                height=settings.height,
            )
            _atomic_publish(temp_dir, final_dir)
            published = True
            await progress.progress("complete", "Export is ready", 1.0)
            return result
        except asyncio.CancelledError:
            raise
        finally:
            if not published and temp_dir.exists():
                shutil.rmtree(temp_dir)


def export_path_for_download(asset_store_path: Path, export_id: str, file_name: str) -> Path:
    if not export_id.startswith("export_") or not all(
        char.isalnum() or char == "_" for char in export_id
    ):
        raise MediaExportError("invalid export id")
    if "/" in file_name or "\\" in file_name or file_name in {"", ".", ".."}:
        raise MediaExportError("invalid export file name")
    path = asset_store_path / "exports" / export_id / file_name
    if not path.is_file():
        raise MediaExportError("export artifact not found")
    return path
