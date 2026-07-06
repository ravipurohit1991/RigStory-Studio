import { describe, expect, it } from "vitest";

import { readSample } from "../../test-utils/samples";
import { aabb, aabbCenter, aabbContainsPoint, aabbFromPoints, aabbIntersects, aabbUnion } from "./aabb";
import {
  AFFINE_IDENTITY,
  affineIsClose,
  applyPoint,
  applyVector,
  fromTrs,
  inverse,
  multiply,
  rotationDegOf
} from "./affine";
import { clamp, lerpAngleDeg, normalizeDeg, shortestDeltaDeg } from "./angles";
import { cubicScalar, cubicScalarDerivative } from "./bezier";
import { centroid, isCcw, isConvex, polygonContainsPoint, signedArea } from "./polygon";
import { SeededRng, seedFromString } from "./rng";
import { add, cross, dot, isClose, length, normalize, perpendicular, rotateDeg, vec2 } from "./vec2";

interface RngCase {
  seed: number;
  uint32: number[];
  floats: number[];
}

interface AngleCase {
  op: string;
  input?: number;
  start?: number;
  end?: number;
  t?: number;
  expected: number;
}

interface TrsSpec {
  position: [number, number];
  rotation_deg: number;
  scale: [number, number];
}

interface Golden {
  rng: { cases: RngCase[]; string_seeds: Record<string, number> };
  angles: AngleCase[];
  affine: {
    parent_trs: TrsSpec;
    child_trs: TrsSpec;
    point: [number, number];
    composed_point: [number, number];
    inverse_round_trip: [number, number];
  };
  bezier: Array<{ p: [number, number, number, number]; t: number; expected: number }>;
}

const golden = readSample("fixtures/math-golden.json") as Golden;

describe("SeededRng golden vectors", () => {
  it("matches the Python sequences exactly", () => {
    for (const rngCase of golden.rng.cases) {
      const rng = new SeededRng(rngCase.seed);
      const uints = Array.from({ length: 8 }, () => rng.nextUint32());
      expect(uints).toEqual(rngCase.uint32);

      const floatRng = new SeededRng(rngCase.seed);
      const floats = Array.from({ length: 4 }, () => floatRng.nextFloat());
      expect(floats).toEqual(rngCase.floats);
    }
  });

  it("derives identical seeds from strings", () => {
    for (const [text, expected] of Object.entries(golden.rng.string_seeds)) {
      expect(seedFromString(text)).toBe(expected);
    }
  });

  it("stays within [0, 1) and respects int bounds", () => {
    const rng = new SeededRng(42);
    for (let index = 0; index < 1000; index += 1) {
      const value = rng.nextFloat();
      expect(value).toBeGreaterThanOrEqual(0);
      expect(value).toBeLessThan(1);
    }
    const intRng = new SeededRng(7);
    const seen = new Set<number>();
    for (let index = 0; index < 200; index += 1) {
      seen.add(intRng.nextInt(3, 6));
    }
    expect([...seen].sort()).toEqual([3, 4, 5]);
  });
});

describe("angle golden vectors", () => {
  it("matches normalize, shortest delta, and lerp results", () => {
    for (const angleCase of golden.angles) {
      if (angleCase.op === "normalize") {
        expect(normalizeDeg(angleCase.input ?? 0)).toBeCloseTo(angleCase.expected, 12);
      } else if (angleCase.op === "shortest_delta") {
        expect(shortestDeltaDeg(angleCase.start ?? 0, angleCase.end ?? 0)).toBeCloseTo(
          angleCase.expected,
          12
        );
      } else if (angleCase.op === "lerp") {
        expect(
          lerpAngleDeg(angleCase.start ?? 0, angleCase.end ?? 0, angleCase.t ?? 0)
        ).toBeCloseTo(angleCase.expected, 12);
      }
    }
  });

  it("interpolates 359 to 1 through zero", () => {
    expect(lerpAngleDeg(359, 1, 0.5)).toBeCloseTo(0, 12);
  });

  it("clamps and rejects inverted ranges", () => {
    expect(clamp(5, 0, 1)).toBe(1);
    expect(() => clamp(0, 1, -1)).toThrow("inverted");
  });
});

describe("affine golden vectors", () => {
  it("matches composed point and inverse round trip", () => {
    const { parent_trs, child_trs, point, composed_point, inverse_round_trip } = golden.affine;
    const parent = fromTrs(
      { x: parent_trs.position[0], y: parent_trs.position[1] },
      parent_trs.rotation_deg,
      parent_trs.scale
    );
    const child = fromTrs(
      { x: child_trs.position[0], y: child_trs.position[1] },
      child_trs.rotation_deg,
      child_trs.scale
    );
    const composed = multiply(parent, child);
    const image = applyPoint(composed, { x: point[0], y: point[1] });
    expect(image.x).toBeCloseTo(composed_point[0], 9);
    expect(image.y).toBeCloseTo(composed_point[1], 9);

    const restored = applyPoint(inverse(composed), image);
    expect(restored.x).toBeCloseTo(inverse_round_trip[0], 9);
    expect(restored.y).toBeCloseTo(inverse_round_trip[1], 9);
  });

  it("inverse times self is identity", () => {
    const transform = fromTrs({ x: 3, y: -2 }, 57, [2, 0.5]);
    expect(affineIsClose(multiply(inverse(transform), transform), AFFINE_IDENTITY, 1e-9)).toBe(
      true
    );
  });

  it("vectors ignore translation and rotation decomposes", () => {
    const transform = fromTrs({ x: 100, y: 100 }, 90);
    const image = applyVector(transform, { x: 1, y: 0 });
    expect(image.x).toBeCloseTo(0, 12);
    expect(image.y).toBeCloseTo(1, 12);
    expect(rotationDegOf(fromTrs({ x: 0, y: 0 }, 33))).toBeCloseTo(33, 12);
  });

  it("rejects singular matrices", () => {
    expect(() => inverse({ a: 1, b: 2, c: 2, d: 4, tx: 0, ty: 0 })).toThrow("singular");
  });
});

describe("bezier golden vectors", () => {
  it("matches scalar evaluation", () => {
    for (const bezierCase of golden.bezier) {
      const [p0, p1, p2, p3] = bezierCase.p;
      expect(cubicScalar(p0, p1, p2, p3, bezierCase.t)).toBeCloseTo(bezierCase.expected, 12);
    }
  });

  it("evaluates the derivative at the endpoints", () => {
    expect(cubicScalarDerivative(0, 0.1, 0.9, 1, 0)).toBeCloseTo(0.3, 12);
    expect(cubicScalarDerivative(0, 0.1, 0.9, 1, 1)).toBeCloseTo(0.3, 12);
  });
});

describe("vec2", () => {
  it("performs basic arithmetic", () => {
    expect(add(vec2(1, 2), vec2(3, -1))).toEqual(vec2(4, 1));
    expect(dot(vec2(1, 2), vec2(3, 4))).toBe(11);
    expect(cross(vec2(1, 0), vec2(0, 1))).toBe(1);
    expect(length(vec2(3, 4))).toBeCloseTo(5, 12);
    expect(isClose(perpendicular(vec2(1, 0)), vec2(0, 1))).toBe(true);
    expect(isClose(rotateDeg(vec2(1, 0), 90), vec2(0, 1))).toBe(true);
  });

  it("rejects normalizing a zero vector", () => {
    expect(() => normalize(vec2(0, 0))).toThrow("zero-length");
  });
});

describe("aabb", () => {
  it("builds, unions, and queries", () => {
    const box = aabbFromPoints([vec2(1, 5), vec2(-2, 3), vec2(0, 7)]);
    expect(box).toEqual({ minX: -2, minY: 3, maxX: 1, maxY: 7 });
    expect(aabbContainsPoint(box, vec2(0, 5))).toBe(true);
    expect(aabbCenter(box)).toEqual(vec2(-0.5, 5));
    const a = aabb(0, 0, 2, 2);
    const b = aabb(2, 1, 3, 3);
    expect(aabbIntersects(a, b)).toBe(true);
    expect(aabbUnion(a, aabb(5, 5, 6, 6))).toEqual({ minX: 0, minY: 0, maxX: 6, maxY: 6 });
    expect(() => aabb(1, 0, 0, 1)).toThrow("invalid AABB");
  });
});

describe("polygon", () => {
  const square = [vec2(0, 0), vec2(1, 0), vec2(1, 1), vec2(0, 1)];
  const lShape = [vec2(0, 0), vec2(2, 0), vec2(2, 1), vec2(1, 1), vec2(1, 2), vec2(0, 2)];

  it("computes area, winding, and centroid", () => {
    expect(signedArea(square)).toBeCloseTo(1, 12);
    expect(isCcw(square)).toBe(true);
    expect(centroid(square)).toEqual(vec2(0.5, 0.5));
  });

  it("checks convexity and containment", () => {
    expect(isConvex(square)).toBe(true);
    expect(isConvex(lShape)).toBe(false);
    expect(polygonContainsPoint(square, vec2(0.5, 0.5))).toBe(true);
    expect(polygonContainsPoint(square, vec2(1.5, 0.5))).toBe(false);
    expect(polygonContainsPoint(lShape, vec2(0.5, 1.5))).toBe(true);
    expect(polygonContainsPoint(lShape, vec2(1.5, 1.5))).toBe(false);
  });
});
