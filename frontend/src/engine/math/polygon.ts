/**
 * Simple polygon helpers. Mirrors backend/app/domain/math2d/polygon.py.
 * Vertices are ordered; no self-intersection checks yet.
 */

import { cross, sub, type Vec2 } from "./vec2";

function requirePolygon(vertices: readonly Vec2[]): void {
  if (vertices.length < 3) {
    throw new Error("a polygon requires at least three vertices");
  }
}

/** Positive for counterclockwise winding (Y-up convention). */
export function signedArea(vertices: readonly Vec2[]): number {
  requirePolygon(vertices);
  let total = 0;
  for (let index = 0; index < vertices.length; index += 1) {
    const current = vertices[index];
    const following = vertices[(index + 1) % vertices.length];
    total += current.x * following.y - following.x * current.y;
  }
  return total / 2;
}

export function isCcw(vertices: readonly Vec2[]): boolean {
  return signedArea(vertices) > 0;
}

export function centroid(vertices: readonly Vec2[]): Vec2 {
  const area = signedArea(vertices);
  if (Math.abs(area) <= 1e-12) {
    throw new Error("cannot compute the centroid of a degenerate polygon");
  }
  let cx = 0;
  let cy = 0;
  for (let index = 0; index < vertices.length; index += 1) {
    const current = vertices[index];
    const following = vertices[(index + 1) % vertices.length];
    const crossTerm = current.x * following.y - following.x * current.y;
    cx += (current.x + following.x) * crossTerm;
    cy += (current.y + following.y) * crossTerm;
  }
  const factor = 1 / (6 * area);
  return { x: cx * factor, y: cy * factor };
}

export function isConvex(vertices: readonly Vec2[]): boolean {
  requirePolygon(vertices);
  let sign = 0;
  const count = vertices.length;
  for (let index = 0; index < count; index += 1) {
    const p0 = vertices[index];
    const p1 = vertices[(index + 1) % count];
    const p2 = vertices[(index + 2) % count];
    const crossValue = cross(sub(p1, p0), sub(p2, p1));
    if (Math.abs(crossValue) <= 1e-12) {
      continue;
    }
    const currentSign = crossValue > 0 ? 1 : -1;
    if (sign === 0) {
      sign = currentSign;
    } else if (sign !== currentSign) {
      return false;
    }
  }
  return true;
}

/** Even-odd ray cast; boundary points count as inside within float limits. */
export function polygonContainsPoint(vertices: readonly Vec2[], point: Vec2): boolean {
  requirePolygon(vertices);
  let inside = false;
  const count = vertices.length;
  for (let index = 0; index < count; index += 1) {
    const current = vertices[index];
    const previous = vertices[(index - 1 + count) % count];
    const crosses = current.y > point.y !== previous.y > point.y;
    if (!crosses) {
      continue;
    }
    const intersectX =
      ((previous.x - current.x) * (point.y - current.y)) / (previous.y - current.y) + current.x;
    if (point.x < intersectX) {
      inside = !inside;
    }
  }
  return inside;
}
