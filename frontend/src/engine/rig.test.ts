import { describe, expect, it } from "vitest";

import { rigSchema } from "../schemas/project";
import { readSample } from "../test-utils/samples";
import { computeBoneEndpoints, validateRig } from "./rig";

interface EndpointGolden {
  origin: [number, number];
  tip: [number, number];
}

interface Golden {
  bone_endpoints: Record<string, Record<string, EndpointGolden>>;
}

const golden = readSample("fixtures/math-golden.json") as Golden;

function loadRig(relativePath: string) {
  return rigSchema.parse(readSample(relativePath));
}

describe("validateRig", () => {
  it("accepts the shared valid fixtures", () => {
    expect(validateRig(loadRig("fixtures/rig-two-bone.json"))).toEqual([]);
    const biped = loadRig("fixtures/rig-canonical-biped.json");
    expect(validateRig(biped)).toEqual([]);
    expect(biped.bones).toHaveLength(25);
  });

  it("detects cycles", () => {
    const rig = loadRig("invalid/rig-cycle.json");
    expect(validateRig(rig).map((issue) => issue.code)).toContain("RIG_CYCLE");
  });

  it("detects duplicate bone ids", () => {
    const rig = loadRig("invalid/rig-duplicate-bone-id.json");
    expect(validateRig(rig).map((issue) => issue.code)).toContain("RIG_DUPLICATE_BONE_ID");
  });

  it("detects missing parents and disconnected bones", () => {
    const rig = loadRig("invalid/rig-missing-parent.json");
    const codes = validateRig(rig).map((issue) => issue.code);
    expect(codes).toContain("RIG_MISSING_PARENT");
    expect(codes).toContain("RIG_DISCONNECTED_BONE");
  });
});

describe("computeBoneEndpoints", () => {
  it("matches the golden endpoints for both shared rigs", () => {
    for (const [fixtureName, expectedByBone] of Object.entries(golden.bone_endpoints)) {
      const rig = loadRig(`fixtures/${fixtureName}`);
      const endpoints = computeBoneEndpoints(rig);
      for (const [boneId, expected] of Object.entries(expectedByBone)) {
        const actual = endpoints.get(boneId);
        expect(actual, `${fixtureName}:${boneId}`).toBeDefined();
        if (actual === undefined) {
          continue;
        }
        expect(actual.origin.x).toBeCloseTo(expected.origin[0], 9);
        expect(actual.origin.y).toBeCloseTo(expected.origin[1], 9);
        expect(actual.tip.x).toBeCloseTo(expected.tip[0], 9);
        expect(actual.tip.y).toBeCloseTo(expected.tip[1], 9);
      }
    }
  });

  it("rejects invalid hierarchies", () => {
    const rig = loadRig("invalid/rig-cycle.json");
    expect(() => computeBoneEndpoints(rig)).toThrow("invalid rig");
  });

  it("is deterministic across repeat evaluation", () => {
    const rig = loadRig("fixtures/rig-canonical-biped.json");
    const first = computeBoneEndpoints(rig);
    const second = computeBoneEndpoints(rig);
    expect([...first.entries()]).toEqual([...second.entries()]);
  });
});
