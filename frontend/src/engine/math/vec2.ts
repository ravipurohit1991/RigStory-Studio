/**
 * Immutable 2D vector. Mirrors backend/app/domain/math2d/vec2.py; both
 * kernels are pinned by samples/fixtures/math-golden.json.
 */

export interface Vec2 {
  readonly x: number;
  readonly y: number;
}

export const VEC2_ZERO: Vec2 = { x: 0, y: 0 };

export function vec2(x: number, y: number): Vec2 {
  return { x, y };
}

export function add(a: Vec2, b: Vec2): Vec2 {
  return { x: a.x + b.x, y: a.y + b.y };
}

export function sub(a: Vec2, b: Vec2): Vec2 {
  return { x: a.x - b.x, y: a.y - b.y };
}

export function neg(v: Vec2): Vec2 {
  return { x: -v.x, y: -v.y };
}

export function scale(v: Vec2, factor: number): Vec2 {
  return { x: v.x * factor, y: v.y * factor };
}

export function dot(a: Vec2, b: Vec2): number {
  return a.x * b.x + a.y * b.y;
}

/** Z component of the 3D cross product; positive when `b` is CCW of `a`. */
export function cross(a: Vec2, b: Vec2): number {
  return a.x * b.y - a.y * b.x;
}

export function lengthSquared(v: Vec2): number {
  return v.x * v.x + v.y * v.y;
}

export function length(v: Vec2): number {
  return Math.hypot(v.x, v.y);
}

export function distance(a: Vec2, b: Vec2): number {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

export function normalize(v: Vec2): Vec2 {
  const magnitude = length(v);
  if (magnitude <= 1e-9) {
    throw new Error("cannot normalize a zero-length vector");
  }
  return { x: v.x / magnitude, y: v.y / magnitude };
}

/** Rotate 90 degrees counterclockwise. */
export function perpendicular(v: Vec2): Vec2 {
  return { x: -v.y, y: v.x };
}

export function lerp(a: Vec2, b: Vec2, t: number): Vec2 {
  return { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t };
}

/** Counterclockwise angle from the +X axis in degrees. */
export function angleDeg(v: Vec2): number {
  return (Math.atan2(v.y, v.x) * 180) / Math.PI;
}

export function rotateDeg(v: Vec2, degrees: number): Vec2 {
  const radians = (degrees * Math.PI) / 180;
  const cosR = Math.cos(radians);
  const sinR = Math.sin(radians);
  return { x: v.x * cosR - v.y * sinR, y: v.x * sinR + v.y * cosR };
}

export function isClose(a: Vec2, b: Vec2, tolerance = 1e-6): boolean {
  return Math.abs(a.x - b.x) <= tolerance && Math.abs(a.y - b.y) <= tolerance;
}
