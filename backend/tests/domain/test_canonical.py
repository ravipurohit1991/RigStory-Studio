from __future__ import annotations

import json

import pytest

from app.domain.canonical import (
    JsonValue,
    canonical_json_dumps,
    canonical_json_pretty,
    model_canonical_json,
)
from app.domain.project import parse_project_document
from tests.sample_paths import load_sample


def test_key_order_is_stable() -> None:
    assert canonical_json_dumps({"b": 1, "a": 2}) == '{"a":2,"b":1}'
    assert canonical_json_dumps({"a": 2, "b": 1}) == '{"a":2,"b":1}'


def test_round_trip_preserves_semantics() -> None:
    value: JsonValue = {
        "name": "Mira",
        "position": [1.5, -2.0],
        "tags": ["a", "b"],
        "nested": {"x": 1},
    }
    assert json.loads(canonical_json_dumps(value)) == value
    assert json.loads(canonical_json_pretty(value)) == value


def test_non_finite_floats_rejected() -> None:
    with pytest.raises(ValueError):
        canonical_json_dumps({"value": float("nan")})
    with pytest.raises(ValueError):
        canonical_json_dumps({"value": float("inf")})


def test_project_document_canonical_round_trip() -> None:
    raw = load_sample("projects/biped-demo.rigstory.json")
    document = parse_project_document(raw)
    first = model_canonical_json(document)
    reparsed = parse_project_document(json.loads(first))
    second = model_canonical_json(reparsed)
    assert first == second


def test_sample_files_are_canonical_on_disk() -> None:
    # Committed samples are written by generate_fixtures.py in canonical
    # pretty form; loading and re-serializing must be byte-stable.
    for relative in (
        "projects/biped-demo.rigstory.json",
        "projects/empty-project.rigstory.json",
        "fixtures/rig-canonical-biped.json",
    ):
        raw = load_sample(relative)
        assert json.loads(canonical_json_pretty(raw)) == raw
