import { computeBoneEndpoints, type RigLike } from "../rig";
import type { Vec2 } from "../math";
import {
  domainToScreen,
  type StageCamera,
  type ViewportSize
} from "./viewport";

export type RigHitTargetKind = "body" | "joint" | "endpoint";

export interface RigHitTarget {
  readonly boneId: string;
  readonly kind: RigHitTargetKind;
  readonly distancePx: number;
}

export interface RigHitTestOptions {
  readonly bodyRadiusPx?: number;
  readonly jointRadiusPx?: number;
  readonly endpointRadiusPx?: number;
}

const DEFAULT_BODY_RADIUS_PX = 7;
const DEFAULT_JOINT_RADIUS_PX = 10;
const DEFAULT_ENDPOINT_RADIUS_PX = 8;

const HIT_PRIORITY: Record<RigHitTargetKind, number> = {
  joint: 0,
  endpoint: 1,
  body: 2
};

function distance(a: Vec2, b: Vec2): number {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

function distanceToSegment(point: Vec2, start: Vec2, end: Vec2): number {
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  const lengthSq = dx * dx + dy * dy;
  if (lengthSq <= 1e-9) {
    return distance(point, start);
  }
  const t = Math.max(0, Math.min(1, ((point.x - start.x) * dx + (point.y - start.y) * dy) / lengthSq));
  return distance(point, { x: start.x + dx * t, y: start.y + dy * t });
}

export function hitTestRig(
  rig: RigLike,
  screenPoint: Vec2,
  camera: StageCamera,
  viewport: ViewportSize,
  options: RigHitTestOptions = {}
): RigHitTarget | null {
  const bodyRadiusPx = options.bodyRadiusPx ?? DEFAULT_BODY_RADIUS_PX;
  const jointRadiusPx = options.jointRadiusPx ?? DEFAULT_JOINT_RADIUS_PX;
  const endpointRadiusPx = options.endpointRadiusPx ?? DEFAULT_ENDPOINT_RADIUS_PX;
  const endpoints = computeBoneEndpoints(rig);
  const hits: RigHitTarget[] = [];

  for (const bone of rig.bones) {
    const endpoint = endpoints.get(bone.id);
    if (endpoint === undefined) {
      continue;
    }
    const originScreen = domainToScreen(endpoint.origin, camera, viewport);
    const tipScreen = domainToScreen(endpoint.tip, camera, viewport);

    const jointDistance = distance(screenPoint, originScreen);
    if (jointDistance <= jointRadiusPx) {
      hits.push({ boneId: bone.id, kind: "joint", distancePx: jointDistance });
    }

    if (bone.length > 0) {
      const endpointDistance = distance(screenPoint, tipScreen);
      if (endpointDistance <= endpointRadiusPx) {
        hits.push({ boneId: bone.id, kind: "endpoint", distancePx: endpointDistance });
      }

      const bodyDistance = distanceToSegment(screenPoint, originScreen, tipScreen);
      if (bodyDistance <= bodyRadiusPx) {
        hits.push({ boneId: bone.id, kind: "body", distancePx: bodyDistance });
      }
    }
  }

  hits.sort((a, b) => a.distancePx - b.distancePx || HIT_PRIORITY[a.kind] - HIT_PRIORITY[b.kind]);
  return hits[0] ?? null;
}
