import { describe, expect, it } from "vitest";

import {
  domainToScreen,
  normalizeViewportSize,
  panCameraByScreenDelta,
  screenToDomain,
  worldBoundsToScreenRect,
  zoomCameraAtScreenPoint,
  type StageCamera
} from "./viewport";

const camera: StageCamera = {
  center: { x: 0, y: 0 },
  zoom: 1,
  pixelsPerUnit: 100
};

describe("viewport coordinate adapter", () => {
  it("maps domain Y-up coordinates into screen Y-down coordinates", () => {
    const viewport = normalizeViewportSize(800, 600, 2);

    expect(domainToScreen({ x: 0, y: 0 }, camera, viewport)).toEqual({ x: 400, y: 300 });
    expect(domainToScreen({ x: 1, y: 1 }, camera, viewport)).toEqual({ x: 500, y: 200 });
    expect(screenToDomain({ x: 500, y: 200 }, camera, viewport)).toEqual({ x: 1, y: 1 });
  });

  it("keeps the zoom anchor stable under the cursor", () => {
    const viewport = normalizeViewportSize(800, 600);
    const anchorScreen = { x: 640, y: 180 };
    const anchorBefore = screenToDomain(anchorScreen, camera, viewport);

    const zoomed = zoomCameraAtScreenPoint(camera, viewport, anchorScreen, 2);
    const anchorAfter = screenToDomain(anchorScreen, zoomed, viewport);

    expect(anchorAfter.x).toBeCloseTo(anchorBefore.x, 12);
    expect(anchorAfter.y).toBeCloseTo(anchorBefore.y, 12);
  });

  it("pans the camera by screen deltas with Y-up semantics", () => {
    const viewport = normalizeViewportSize(800, 600);
    const panned = panCameraByScreenDelta(camera, { x: 100, y: -50 }, viewport);

    expect(panned.center.x).toBeCloseTo(-1);
    expect(panned.center.y).toBeCloseTo(-0.5);
  });

  it("normalizes unusable viewport measurements", () => {
    expect(normalizeViewportSize(0, -20, 0)).toEqual({
      width: 1,
      height: 1,
      devicePixelRatio: 1
    });
  });

  it("converts world bounds to a screen rectangle", () => {
    const viewport = normalizeViewportSize(800, 600);
    const rect = worldBoundsToScreenRect([-1, -1, 2, 3], camera, viewport);

    expect(rect).toEqual({ x: 300, y: 0, width: 300, height: 400 });
  });
});
