/** Angle helpers. Serialized angles are counterclockwise degrees. */

export function degToRad(degrees: number): number {
  return (degrees * Math.PI) / 180;
}

export function radToDeg(radians: number): number {
  return (radians * 180) / Math.PI;
}

/**
 * Normalize to the half-open interval (-180, 180].
 * JavaScript `%` truncates toward zero exactly like Python `math.fmod`,
 * so both kernels wrap identically.
 */
export function normalizeDeg(degrees: number): number {
  let wrapped = degrees % 360;
  if (wrapped > 180) {
    wrapped -= 360;
  } else if (wrapped <= -180) {
    wrapped += 360;
  }
  return wrapped;
}

/** Signed shortest rotation from `start` to `end` in (-180, 180]. */
export function shortestDeltaDeg(start: number, end: number): number {
  return normalizeDeg(end - start);
}

/** Interpolate along the shortest arc; 359 to 1 passes through 0. */
export function lerpAngleDeg(start: number, end: number, t: number): number {
  return normalizeDeg(start + shortestDeltaDeg(start, end) * t);
}

export function clamp(value: number, minimum: number, maximum: number): number {
  if (minimum > maximum) {
    throw new Error(`clamp range is inverted: [${minimum}, ${maximum}]`);
  }
  return Math.max(minimum, Math.min(maximum, value));
}
