/**
 * Canvas 2D renderer for the native runtime.
 *
 * This module renders a validated project document without the editor UI,
 * React, Fluent UI, or PixiJS. It mirrors the editor's attachment geometry so
 * exported playback matches what the editor shows for rigid and mesh parts.
 */

import { applyClipPoseToRig, evaluateClip } from "../engine/clip";
import {
  applyPoint,
  fromTrs,
  multiply,
  type Affine2,
  type Vec2
} from "../engine/math";
import { skinMeshAttachment } from "../engine/meshSkinning";
import { computeBoneEndpoints, computeWorldTransforms, transformToAffine } from "../engine/rig";
import type {
  AnimationClip,
  AttachmentDefinition,
  CharacterDefinition,
  PrimitiveAttachment,
  ProjectDocument,
  SceneDefinition
} from "../schemas/project";

/** Minimal 2D context surface used by the runtime; matches CanvasRenderingContext2D. */
export interface Context2DLike {
  fillStyle: string | CanvasGradient | CanvasPattern;
  strokeStyle: string | CanvasGradient | CanvasPattern;
  globalAlpha: number;
  lineWidth: number;
  lineCap: CanvasLineCap;
  clearRect(x: number, y: number, width: number, height: number): void;
  fillRect(x: number, y: number, width: number, height: number): void;
  beginPath(): void;
  moveTo(x: number, y: number): void;
  lineTo(x: number, y: number): void;
  closePath(): void;
  fill(): void;
  stroke(): void;
}

export interface ResolvedActor {
  readonly actorId: string;
  readonly displayName: string;
  readonly character: CharacterDefinition;
  readonly rootTransform: {
    readonly position: readonly [number, number];
    readonly rotation_deg: number;
    readonly scale: readonly [number, number];
  };
}

export interface RuntimeClipSource {
  readonly document: ProjectDocument;
  readonly clip: AnimationClip;
  readonly scene: SceneDefinition;
  readonly actors: readonly ResolvedActor[];
}

export class RuntimeSourceError extends Error {}

/** Resolve a clip plus everything needed to render it from a project document. */
export function resolveClipSource(
  document: ProjectDocument,
  clipId?: string
): RuntimeClipSource {
  const clip = clipId
    ? document.clips.find((candidate) => candidate.id === clipId)
    : document.clips[0];
  if (clip === undefined) {
    throw new RuntimeSourceError(
      clipId ? `clip '${clipId}' is not in this project` : "this project has no clips"
    );
  }
  const scene = document.scenes.find((candidate) => candidate.id === clip.scene_id);
  if (scene === undefined) {
    throw new RuntimeSourceError(`clip '${clip.id}' references missing scene '${clip.scene_id}'`);
  }
  const charactersById = new Map(document.characters.map((character) => [character.id, character]));
  const actors = scene.actors.map((actor) => {
    const character = charactersById.get(actor.character_id);
    if (character === undefined) {
      throw new RuntimeSourceError(
        `actor '${actor.id}' references missing character '${actor.character_id}'`
      );
    }
    return {
      actorId: actor.id,
      displayName: actor.display_name,
      character,
      rootTransform: actor.root_transform
    };
  });
  return { document, clip, scene, actors };
}

export interface WorldToCanvasMap {
  readonly scale: number;
  readonly offsetX: number;
  readonly offsetY: number;
  readonly height: number;
}

/** Fit Y-up world bounds into a Y-down canvas with uniform scale and padding. */
export function computeWorldToCanvas(
  worldBounds: readonly [number, number, number, number],
  width: number,
  height: number,
  paddingRatio = 0.05
): WorldToCanvasMap {
  const [minX, minY, maxX, maxY] = worldBounds;
  const worldWidth = Math.max(maxX - minX, 1e-6);
  const worldHeight = Math.max(maxY - minY, 1e-6);
  const padding = Math.min(width, height) * paddingRatio;
  const scale = Math.min(
    (width - padding * 2) / worldWidth,
    (height - padding * 2) / worldHeight
  );
  const offsetX = (width - worldWidth * scale) / 2 - minX * scale;
  const offsetY = (height - worldHeight * scale) / 2 + maxY * scale;
  return { scale, offsetX, offsetY, height };
}

export function worldPointToCanvas(map: WorldToCanvasMap, point: Vec2): Vec2 {
  return { x: point.x * map.scale + map.offsetX, y: map.offsetY - point.y * map.scale };
}

/** Outline points for a primitive attachment in attachment-local space. */
export function primitiveOutlinePoints(
  primitive: PrimitiveAttachment,
  pivot: readonly [number, number]
): Vec2[] {
  const [width, height] = primitive.size;
  const left = -pivot[0];
  const right = width - pivot[0];
  const bottom = -height / 2 - pivot[1];
  const top = height / 2 - pivot[1];

  if (primitive.shape === "ellipse") {
    return Array.from({ length: 24 }, (_value, index) => {
      const angle = (Math.PI * 2 * index) / 24;
      return {
        x: left + width / 2 + Math.cos(angle) * (width / 2),
        y: Math.sin(angle) * (height / 2) - pivot[1]
      };
    });
  }
  if (primitive.shape === "rectangle") {
    return [
      { x: left, y: bottom },
      { x: right, y: bottom },
      { x: right, y: top },
      { x: left, y: top }
    ];
  }
  // Capsule: two half circles joined by straight edges, matching the editor.
  return Array.from({ length: 24 }, (_value, index) => {
    const radius = height / 2;
    const straight = Math.max(0, width - height);
    const angle =
      index < 12
        ? Math.PI / 2 - (Math.PI * index) / 11
        : -Math.PI / 2 - (Math.PI * (index - 12)) / 11;
    const centerX = index < 12 ? left + straight + radius : left + radius;
    return { x: centerX + Math.cos(angle) * radius, y: Math.sin(angle) * radius - pivot[1] };
  });
}

function inferredPrimitiveForBone(boneLength: number, attachmentId: string): PrimitiveAttachment {
  if (attachmentId.includes("head")) {
    return { shape: "ellipse", size: [0.42, 0.36], fill: "#f0c8a0", opacity: 1 };
  }
  if (attachmentId.includes("torso") || attachmentId.includes("pelvis")) {
    return { shape: "rectangle", size: [0.5, 0.34], fill: "#6b8fa8", opacity: 0.92 };
  }
  return { shape: "capsule", size: [Math.max(0.18, boneLength), 0.16], fill: "#e6b17a", opacity: 1 };
}

function fillPolygon(ctx: Context2DLike, points: readonly Vec2[]): void {
  if (points.length < 3) {
    return;
  }
  ctx.beginPath();
  ctx.moveTo(points[0].x, points[0].y);
  for (const point of points.slice(1)) {
    ctx.lineTo(point.x, point.y);
  }
  ctx.closePath();
  ctx.fill();
}

export interface RenderFrameOptions {
  readonly width: number;
  readonly height: number;
  /** CSS color, or null for a transparent frame. */
  readonly background?: string | null;
  /** Draw bone lines for characters with no visible attachments. */
  readonly drawBoneFallback?: boolean;
}

/** Render one deterministic frame of the clip at `time` into a 2D context. */
export function renderClipFrame(
  ctx: Context2DLike,
  source: RuntimeClipSource,
  time: number,
  options: RenderFrameOptions
): void {
  const { width, height } = options;
  ctx.clearRect(0, 0, width, height);
  if (options.background != null) {
    ctx.globalAlpha = 1;
    ctx.fillStyle = options.background;
    ctx.fillRect(0, 0, width, height);
  }
  const map = computeWorldToCanvas(source.scene.world_bounds, width, height);
  drawSceneObjects(ctx, source.scene, map);

  const pose = evaluateClip(source.clip, time);
  for (const actor of source.actors) {
    const actorPose = pose.actors[actor.actorId];
    const rootPosition = actorPose?.root_translation ?? actor.rootTransform.position;
    const actorMatrix = fromTrs(
      { x: rootPosition[0], y: rootPosition[1] },
      actor.rootTransform.rotation_deg,
      actor.rootTransform.scale
    );
    const posedRig = applyClipPoseToRig(actor.character.rig, pose, actor.actorId);
    drawActor(ctx, actor, posedRig, actorMatrix, map, options.drawBoneFallback ?? true);
  }
  ctx.globalAlpha = 1;
}

function drawSceneObjects(
  ctx: Context2DLike,
  scene: SceneDefinition,
  map: WorldToCanvasMap
): void {
  for (const object of scene.objects) {
    if (!object.visible) {
      continue;
    }
    if (object.visual.type === "rectangle") {
      const [minX, minY, maxX, maxY] = object.bounds;
      const topLeft = worldPointToCanvas(map, { x: minX, y: maxY });
      const bottomRight = worldPointToCanvas(map, { x: maxX, y: minY });
      ctx.globalAlpha = object.visual.opacity;
      ctx.fillStyle = object.visual.fill;
      ctx.fillRect(
        topLeft.x,
        topLeft.y,
        bottomRight.x - topLeft.x,
        bottomRight.y - topLeft.y
      );
    } else if (object.visual.type === "polygon") {
      ctx.globalAlpha = object.visual.opacity;
      ctx.fillStyle = object.visual.fill;
      fillPolygon(
        ctx,
        object.visual.vertices.map(([x, y]) => worldPointToCanvas(map, { x, y }))
      );
    }
    // svg/png visuals need asset payloads; the runtime skips them by design.
  }
}

type PosedRig = ResolvedActor["character"]["rig"];

function drawActor(
  ctx: Context2DLike,
  actor: ResolvedActor,
  posedRig: PosedRig,
  actorMatrix: Affine2,
  map: WorldToCanvasMap,
  drawBoneFallback: boolean
): void {
  const worlds = computeWorldTransforms(posedRig);
  const bonesById = new Map(posedRig.bones.map((bone) => [bone.id, bone]));
  const visibleAttachments = actor.character.attachments
    .filter((attachment) => attachment.visible)
    .sort((a, b) => a.z_index - b.z_index || a.id.localeCompare(b.id));

  for (const attachment of visibleAttachments) {
    const boneWorld = worlds.get(attachment.bone_id);
    const bone = bonesById.get(attachment.bone_id);
    if (boneWorld === undefined || bone === undefined) {
      continue;
    }
    const matrix = multiply(actorMatrix, multiply(boneWorld, transformToAffine(attachment.transform)));
    if (attachment.kind === "mesh" && attachment.mesh !== null) {
      drawMesh(ctx, attachment, posedRig, matrix, map);
      continue;
    }
    const primitive = attachment.primitive ?? inferredPrimitiveForBone(bone.length, attachment.id);
    ctx.globalAlpha = primitive.opacity;
    ctx.fillStyle = primitive.fill;
    fillPolygon(
      ctx,
      primitiveOutlinePoints(primitive, attachment.pivot).map((point) =>
        worldPointToCanvas(map, applyPoint(matrix, point))
      )
    );
  }

  if (visibleAttachments.length === 0 && drawBoneFallback) {
    const endpoints = computeBoneEndpoints(posedRig);
    ctx.globalAlpha = 1;
    ctx.strokeStyle = "#355c7d";
    ctx.lineWidth = Math.max(2, map.scale * 0.05);
    ctx.lineCap = "round";
    for (const bone of posedRig.bones) {
      const endpoint = endpoints.get(bone.id);
      if (endpoint === undefined || bone.length === 0) {
        continue;
      }
      const origin = worldPointToCanvas(map, applyPoint(actorMatrix, endpoint.origin));
      const tip = worldPointToCanvas(map, applyPoint(actorMatrix, endpoint.tip));
      ctx.beginPath();
      ctx.moveTo(origin.x, origin.y);
      ctx.lineTo(tip.x, tip.y);
      ctx.stroke();
    }
  }
}

function drawMesh(
  ctx: Context2DLike,
  attachment: AttachmentDefinition,
  posedRig: PosedRig,
  matrix: Affine2,
  map: WorldToCanvasMap
): void {
  if (attachment.mesh === null) {
    return;
  }
  const vertices = skinMeshAttachment(attachment, posedRig);
  ctx.globalAlpha = attachment.mesh.opacity;
  ctx.fillStyle = attachment.mesh.fill;
  for (const triangle of attachment.mesh.triangles) {
    fillPolygon(
      ctx,
      triangle.indices.map((index) =>
        worldPointToCanvas(map, applyPoint(matrix, vertices[index]))
      )
    );
  }
}
