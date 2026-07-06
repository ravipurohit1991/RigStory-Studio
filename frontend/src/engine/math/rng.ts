/**
 * Deterministic seeded random helper (mulberry32).
 *
 * Bit-identical to backend/app/domain/math2d/rng.py; shared golden vectors
 * in samples/fixtures/math-golden.json pin both implementations. Do not
 * change this algorithm without regenerating goldens and writing an ADR:
 * seeded variation must stay reproducible across releases.
 */

export class SeededRng {
  private state: number;

  constructor(seed: number) {
    this.state = seed >>> 0;
  }

  nextUint32(): number {
    this.state = (this.state + 0x6d2b79f5) >>> 0;
    let t = this.state;
    t = Math.imul(t ^ (t >>> 15), t | 1) >>> 0;
    t = (t ^ ((t + Math.imul(t ^ (t >>> 7), t | 61)) >>> 0)) >>> 0;
    return (t ^ (t >>> 14)) >>> 0;
  }

  /** Uniform float in [0, 1). */
  nextFloat(): number {
    return this.nextUint32() / 4294967296;
  }

  nextRange(minimum: number, maximum: number): number {
    return minimum + (maximum - minimum) * this.nextFloat();
  }

  nextInt(minimum: number, maximumExclusive: number): number {
    if (maximumExclusive <= minimum) {
      throw new Error("maximumExclusive must be greater than minimum");
    }
    const span = maximumExclusive - minimum;
    return minimum + Math.floor(this.nextFloat() * span);
  }
}

/** FNV-1a 32-bit hash over UTF-8 bytes for deriving seeds from stable IDs. */
export function seedFromString(text: string): number {
  const bytes = new TextEncoder().encode(text);
  let value = 0x811c9dc5;
  for (const byte of bytes) {
    value ^= byte;
    value = Math.imul(value, 0x01000193) >>> 0;
  }
  return value >>> 0;
}
