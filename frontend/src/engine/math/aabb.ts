/** Axis-aligned bounding box. Mirrors backend/app/domain/math2d/aabb.py. */

import type { Vec2 } from "./vec2";

export interface Aabb {
  readonly minX: number;
  readonly minY: number;
  readonly maxX: number;
  readonly maxY: number;
}

export function aabb(minX: number, minY: number, maxX: number, maxY: number): Aabb {
  if (minX > maxX || minY > maxY) {
    throw new Error(`invalid AABB: min (${minX}, ${minY}) exceeds max (${maxX}, ${maxY})`);
  }
  return { minX, minY, maxX, maxY };
}

export function aabbFromPoints(points: readonly Vec2[]): Aabb {
  if (points.length === 0) {
    throw new Error("cannot build an AABB from zero points");
  }
  let minX = points[0].x;
  let minY = points[0].y;
  let maxX = points[0].x;
  let maxY = points[0].y;
  for (const point of points.slice(1)) {
    minX = Math.min(minX, point.x);
    minY = Math.min(minY, point.y);
    maxX = Math.max(maxX, point.x);
    maxY = Math.max(maxY, point.y);
  }
  return { minX, minY, maxX, maxY };
}

export function aabbWidth(box: Aabb): number {
  return box.maxX - box.minX;
}

export function aabbHeight(box: Aabb): number {
  return box.maxY - box.minY;
}

export function aabbCenter(box: Aabb): Vec2 {
  return { x: (box.minX + box.maxX) / 2, y: (box.minY + box.maxY) / 2 };
}

export function aabbContainsPoint(box: Aabb, point: Vec2): boolean {
  return (
    box.minX <= point.x && point.x <= box.maxX && box.minY <= point.y && point.y <= box.maxY
  );
}

export function aabbIntersects(a: Aabb, b: Aabb): boolean {
  return a.minX <= b.maxX && b.minX <= a.maxX && a.minY <= b.maxY && b.minY <= a.maxY;
}

export function aabbUnion(a: Aabb, b: Aabb): Aabb {
  return {
    minX: Math.min(a.minX, b.minX),
    minY: Math.min(a.minY, b.minY),
    maxX: Math.max(a.maxX, b.maxX),
    maxY: Math.max(a.maxY, b.maxY)
  };
}

export function aabbExpanded(box: Aabb, margin: number): Aabb {
  return {
    minX: box.minX - margin,
    minY: box.minY - margin,
    maxX: box.maxX + margin,
    maxY: box.maxY + margin
  };
}
