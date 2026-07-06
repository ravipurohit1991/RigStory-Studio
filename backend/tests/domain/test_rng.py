from __future__ import annotations

import pytest

from app.domain.math2d.rng import SeededRng, seed_from_string
from tests.sample_paths import load_sample


def test_matches_golden_vectors() -> None:
    golden = load_sample("fixtures/math-golden.json")
    rng_section = golden["rng"]
    assert isinstance(rng_section, dict)
    cases = rng_section["cases"]
    assert isinstance(cases, list)
    for case in cases:
        assert isinstance(case, dict)
        seed = case["seed"]
        assert isinstance(seed, int)
        rng = SeededRng(seed)
        assert [rng.next_uint32() for _ in range(8)] == case["uint32"]
        rng = SeededRng(seed)
        assert [rng.next_float() for _ in range(4)] == case["floats"]

    string_seeds = rng_section["string_seeds"]
    assert isinstance(string_seeds, dict)
    for text, expected in string_seeds.items():
        assert seed_from_string(text) == expected


def test_fnv1a_known_values() -> None:
    # FNV-1a 32-bit offset basis and a published single-byte value.
    assert seed_from_string("") == 0x811C9DC5
    assert seed_from_string("a") == 0xE40C292C


def test_same_seed_same_sequence() -> None:
    first = SeededRng(987654321)
    second = SeededRng(987654321)
    assert [first.next_uint32() for _ in range(100)] == [second.next_uint32() for _ in range(100)]


def test_float_range() -> None:
    rng = SeededRng(42)
    for _ in range(1000):
        value = rng.next_float()
        assert 0.0 <= value < 1.0


def test_next_int_bounds() -> None:
    rng = SeededRng(7)
    values = {rng.next_int(3, 6) for _ in range(200)}
    assert values == {3, 4, 5}
    with pytest.raises(ValueError, match="greater than"):
        rng.next_int(5, 5)


def test_next_range() -> None:
    rng = SeededRng(11)
    for _ in range(100):
        value = rng.next_range(-2.0, 2.0)
        assert -2.0 <= value < 2.0
