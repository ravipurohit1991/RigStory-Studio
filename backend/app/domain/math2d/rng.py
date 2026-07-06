"""Deterministic seeded random helper.

Implements the mulberry32 generator with 32-bit unsigned arithmetic so the
TypeScript engine kernel produces bit-identical sequences from the same seed.
Shared golden vectors in ``samples/fixtures/math-golden.json`` pin both
implementations. Do not change this algorithm without regenerating goldens
and writing an ADR: seeded variation must stay reproducible across releases.
"""

from __future__ import annotations

_MASK32 = 0xFFFFFFFF


class SeededRng:
    def __init__(self, seed: int) -> None:
        self._state = seed & _MASK32

    def next_uint32(self) -> int:
        self._state = (self._state + 0x6D2B79F5) & _MASK32
        t = self._state
        t = ((t ^ (t >> 15)) * (t | 1)) & _MASK32
        t = (t ^ (t + (((t ^ (t >> 7)) * (t | 61)) & _MASK32))) & _MASK32
        return (t ^ (t >> 14)) & _MASK32

    def next_float(self) -> float:
        """Uniform float in [0, 1)."""
        return self.next_uint32() / 4294967296.0

    def next_range(self, minimum: float, maximum: float) -> float:
        return minimum + (maximum - minimum) * self.next_float()

    def next_int(self, minimum: int, maximum_exclusive: int) -> int:
        if maximum_exclusive <= minimum:
            raise ValueError("maximum_exclusive must be greater than minimum")
        span = maximum_exclusive - minimum
        return minimum + int(self.next_float() * span)


def seed_from_string(text: str) -> int:
    """FNV-1a 32-bit hash for deriving seeds from stable IDs."""
    value = 0x811C9DC5
    for byte in text.encode("utf-8"):
        value ^= byte
        value = (value * 0x01000193) & _MASK32
    return value
