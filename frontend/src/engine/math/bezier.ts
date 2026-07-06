/** Cubic Bezier evaluation. Mirrors backend/app/domain/math2d/bezier.py. */

import type { Vec2 } from "./vec2";

export function cubicScalar(p0: number, p1: number, p2: number, p3: number, t: number): number {
  const u = 1 - t;
  return u * u * u * p0 + 3 * u * u * t * p1 + 3 * u * t * t * p2 + t * t * t * p3;
}

export function cubicScalarDerivative(
  p0: number,
  p1: number,
  p2: number,
  p3: number,
  t: number
): number {
  const u = 1 - t;
  return 3 * u * u * (p1 - p0) + 6 * u * t * (p2 - p1) + 3 * t * t * (p3 - p2);
}

export function cubicPoint(p0: Vec2, p1: Vec2, p2: Vec2, p3: Vec2, t: number): Vec2 {
  return {
    x: cubicScalar(p0.x, p1.x, p2.x, p3.x, t),
    y: cubicScalar(p0.y, p1.y, p2.y, p3.y, t)
  };
}

export function cubicPointDerivative(p0: Vec2, p1: Vec2, p2: Vec2, p3: Vec2, t: number): Vec2 {
  return {
    x: cubicScalarDerivative(p0.x, p1.x, p2.x, p3.x, t),
    y: cubicScalarDerivative(p0.y, p1.y, p2.y, p3.y, t)
  };
}
