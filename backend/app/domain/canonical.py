"""Canonical JSON serialization with stable ordering.

Canonical output is used for hashing, revision comparison, and byte-stable
exports. Two semantically equal documents must always serialize to the same
bytes: keys are sorted, separators are fixed, and NaN/Infinity are rejected.
"""

from __future__ import annotations

import json

from pydantic import BaseModel

type JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]


def canonical_json_dumps(value: JsonValue) -> str:
    """Compact canonical form used for hashing and equality checks."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def canonical_json_pretty(value: JsonValue) -> str:
    """Readable canonical form used for files committed to the repository."""
    return (
        json.dumps(
            value,
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )


def canonical_json_bytes(value: JsonValue) -> bytes:
    return canonical_json_dumps(value).encode("utf-8")


def model_canonical_json(model: BaseModel) -> str:
    dumped: JsonValue = model.model_dump(mode="json")
    return canonical_json_dumps(dumped)
