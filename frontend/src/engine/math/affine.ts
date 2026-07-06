/**
 * 2D affine matrix mirroring backend/app/domain/math2d/affine.py.
 *
 *     | a  c  tx |
 *     | b  d  ty |
 *     | 0  0  1  |
 *
 * Columns (a, b) and (c, d) are the images of the X and Y basis vectors.
 * Affine matrices are closed under composition, unlike TRS transforms with
 * non-uniform scale, so world transforms are always composed as matrices.
 */

import { degToRad, radToDeg } from "./angles";
import type { Vec2 } from "./vec2";

export interface Affine2 {
  readonly a: number;
  readonly b: number;
  readonly c: number;
  readonly d: number;
  readonly tx: number;
  readonly ty: number;
}

export const AFFINE_IDENTITY: Affine2 = { a: 1, b: 0, c: 0, d: 1, tx: 0, ty: 0 };

export function fromTrs(
  translation: Vec2,
  rotationDeg: number,
  scale: readonly [number, number] = [1, 1]
): Affine2 {
  const radians = degToRad(rotationDeg);
  const cosR = Math.cos(radians);
  const sinR = Math.sin(radians);
  const [sx, sy] = scale;
  return {
    a: cosR * sx,
    b: sinR * sx,
    c: -sinR * sy,
    d: cosR * sy,
    tx: translation.x,
    ty: translation.y
  };
}

/** Returns `m @ n` (apply `n` first, then `m`). */
export function multiply(m: Affine2, n: Affine2): Affine2 {
  return {
    a: m.a * n.a + m.c * n.b,
    b: m.b * n.a + m.d * n.b,
    c: m.a * n.c + m.c * n.d,
    d: m.b * n.c + m.d * n.d,
    tx: m.a * n.tx + m.c * n.ty + m.tx,
    ty: m.b * n.tx + m.d * n.ty + m.ty
  };
}

export function determinant(m: Affine2): number {
  return m.a * m.d - m.b * m.c;
}

export function inverse(m: Affine2): Affine2 {
  const det = determinant(m);
  if (Math.abs(det) <= 1e-12) {
    throw new Error("matrix is singular and cannot be inverted");
  }
  const invDet = 1 / det;
  const a = m.d * invDet;
  const b = -m.b * invDet;
  const c = -m.c * invDet;
  const d = m.a * invDet;
  return {
    a,
    b,
    c,
    d,
    tx: -(a * m.tx + c * m.ty),
    ty: -(b * m.tx + d * m.ty)
  };
}

export function applyPoint(m: Affine2, point: Vec2): Vec2 {
  return {
    x: m.a * point.x + m.c * point.y + m.tx,
    y: m.b * point.x + m.d * point.y + m.ty
  };
}

/** Transform a direction: rotation and scale apply, translation does not. */
export function applyVector(m: Affine2, vector: Vec2): Vec2 {
  return {
    x: m.a * vector.x + m.c * vector.y,
    y: m.b * vector.x + m.d * vector.y
  };
}

export function translationOf(m: Affine2): Vec2 {
  return { x: m.tx, y: m.ty };
}

/** Rotation of the X basis vector in degrees. */
export function rotationDegOf(m: Affine2): number {
  return radToDeg(Math.atan2(m.b, m.a));
}

export function affineIsClose(m: Affine2, n: Affine2, tolerance = 1e-9): boolean {
  return (
    Math.abs(m.a - n.a) <= tolerance &&
    Math.abs(m.b - n.b) <= tolerance &&
    Math.abs(m.c - n.c) <= tolerance &&
    Math.abs(m.d - n.d) <= tolerance &&
    Math.abs(m.tx - n.tx) <= tolerance &&
    Math.abs(m.ty - n.ty) <= tolerance
  );
}
