import { describe, expect, it } from "vitest";

import { rigSchema } from "../../schemas/project";
import { readSample } from "../../test-utils/samples";
import { computeBoneEndpoints } from "../rig";
import { domainToScreen, normalizeViewportSize, type StageCamera } from "./viewport";
import { hitTestRig } from "./rigHitTest";

function loadRig(relativePath: string) {
  return rigSchema.parse(readSample(relativePath));
}

const camera: StageCamera = {
  center: { x: 0, y: 0 },
  zoom: 1,
  pixelsPerUnit: 20
};
const viewport = normalizeViewportSize(400, 400);

describe("hitTestRig", () => {
  it("detects joint, body, and endpoint hits", () => {
    const rig = loadRig("fixtures/rig-two-bone.json");
    const endpoints = computeBoneEndpoints(rig);
    const boneA = endpoints.get("bone_a");
    expect(boneA).toBeDefined();
    if (boneA === undefined) {
      return;
    }

    const jointScreen = domainToScreen(boneA.origin, camera, viewport);
    const bodyScreen = domainToScreen(
      {
        x: (boneA.origin.x + boneA.tip.x) / 2,
        y: (boneA.origin.y + boneA.tip.y) / 2
      },
      camera,
      viewport
    );
    const tipScreen = domainToScreen(boneA.tip, camera, viewport);
    const segment = { x: tipScreen.x - jointScreen.x, y: tipScreen.y - jointScreen.y };
    const segmentLength = Math.hypot(segment.x, segment.y);
    const endpointProbe = {
      x: tipScreen.x + (-segment.y / segmentLength) * 6,
      y: tipScreen.y + (segment.x / segmentLength) * 6
    };

    expect(hitTestRig(rig, jointScreen, camera, viewport)).toMatchObject({
      boneId: "bone_a",
      kind: "joint"
    });
    expect(hitTestRig(rig, bodyScreen, camera, viewport)).toMatchObject({
      boneId: "bone_a",
      kind: "body"
    });
    expect(
      hitTestRig(rig, endpointProbe, camera, viewport, {
        bodyRadiusPx: 4,
        endpointRadiusPx: 8,
        jointRadiusPx: 4
      })
    ).toMatchObject({
      boneId: "bone_a",
      kind: "endpoint"
    });
  });

  it("returns null when the pointer is outside hit radii", () => {
    const rig = loadRig("fixtures/rig-two-bone.json");

    expect(hitTestRig(rig, { x: 4, y: 390 }, camera, viewport)).toBeNull();
  });
});
