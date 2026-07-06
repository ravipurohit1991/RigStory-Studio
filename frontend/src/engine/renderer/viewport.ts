import type { Vec2 } from "../math";

export interface ViewportSize {
  readonly width: number;
  readonly height: number;
  readonly devicePixelRatio: number;
}

export interface StageCamera {
  readonly center: Vec2;
  readonly zoom: number;
  readonly pixelsPerUnit: number;
}

export type WorldBounds = readonly [number, number, number, number];

export const DEFAULT_STAGE_CAMERA: StageCamera = {
  center: { x: 0, y: 1.6 },
  zoom: 1,
  pixelsPerUnit: 160
};

export const DEFAULT_CAMERA_BOUNDS: WorldBounds = [-2.5, -0.35, 2.5, 4.25];

export function normalizeViewportSize(
  width: number,
  height: number,
  devicePixelRatio = 1
): ViewportSize {
  return {
    width: Math.max(1, Math.floor(width)),
    height: Math.max(1, Math.floor(height)),
    devicePixelRatio: Math.max(1, devicePixelRatio)
  };
}

export function clampZoom(zoom: number, minZoom = 0.25, maxZoom = 5): number {
  return Math.min(maxZoom, Math.max(minZoom, zoom));
}

export function pixelsPerWorldUnit(camera: StageCamera): number {
  return camera.pixelsPerUnit * camera.zoom;
}

export function domainToScreen(point: Vec2, camera: StageCamera, viewport: ViewportSize): Vec2 {
  const scale = pixelsPerWorldUnit(camera);
  return {
    x: viewport.width / 2 + (point.x - camera.center.x) * scale,
    y: viewport.height / 2 - (point.y - camera.center.y) * scale
  };
}

export function screenToDomain(point: Vec2, camera: StageCamera, viewport: ViewportSize): Vec2 {
  const scale = pixelsPerWorldUnit(camera);
  return {
    x: camera.center.x + (point.x - viewport.width / 2) / scale,
    y: camera.center.y - (point.y - viewport.height / 2) / scale
  };
}

export function panCameraByScreenDelta(
  camera: StageCamera,
  deltaScreen: Vec2,
  viewport: ViewportSize
): StageCamera {
  const domainStart = screenToDomain({ x: 0, y: 0 }, camera, viewport);
  const domainEnd = screenToDomain(deltaScreen, camera, viewport);
  return {
    ...camera,
    center: {
      x: camera.center.x - (domainEnd.x - domainStart.x),
      y: camera.center.y - (domainEnd.y - domainStart.y)
    }
  };
}

export function zoomCameraAtScreenPoint(
  camera: StageCamera,
  viewport: ViewportSize,
  screenPoint: Vec2,
  requestedZoom: number
): StageCamera {
  const anchorBefore = screenToDomain(screenPoint, camera, viewport);
  const zoom = clampZoom(requestedZoom);
  const scale = camera.pixelsPerUnit * zoom;
  return {
    ...camera,
    zoom,
    center: {
      x: anchorBefore.x - (screenPoint.x - viewport.width / 2) / scale,
      y: anchorBefore.y + (screenPoint.y - viewport.height / 2) / scale
    }
  };
}

export function wheelDeltaToZoom(camera: StageCamera, deltaY: number): number {
  return clampZoom(camera.zoom * Math.pow(1.0015, -deltaY));
}

export function visibleWorldBounds(camera: StageCamera, viewport: ViewportSize): WorldBounds {
  const topLeft = screenToDomain({ x: 0, y: 0 }, camera, viewport);
  const bottomRight = screenToDomain({ x: viewport.width, y: viewport.height }, camera, viewport);
  return [topLeft.x, bottomRight.y, bottomRight.x, topLeft.y];
}

export function worldBoundsToScreenRect(
  bounds: WorldBounds,
  camera: StageCamera,
  viewport: ViewportSize
): { readonly x: number; readonly y: number; readonly width: number; readonly height: number } {
  const [minX, minY, maxX, maxY] = bounds;
  const topLeft = domainToScreen({ x: minX, y: maxY }, camera, viewport);
  const bottomRight = domainToScreen({ x: maxX, y: minY }, camera, viewport);
  return {
    x: topLeft.x,
    y: topLeft.y,
    width: bottomRight.x - topLeft.x,
    height: bottomRight.y - topLeft.y
  };
}
