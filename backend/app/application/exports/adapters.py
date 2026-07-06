"""Third-party format adapter contract.

Adapters translate a native project document into an external format. They
live outside the domain package on purpose: the native schema never depends on
an external format, and an adapter never mutates project state. No adapter
ships enabled by default — each target format requires its own licensing
review before an implementation may be added (see
``docs/adr/0008-third-party-format-adapters.md``). Exact Spine parity is
explicitly not promised.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.domain.project import ProjectDocument


@dataclass(frozen=True, slots=True)
class AdapterCapability:
    """What an adapter can represent for a given document."""

    supported: bool
    detail: str = ""
    unsupported_features: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AdapterExportResult:
    """Files produced by an adapter, keyed by relative output path."""

    files: dict[str, bytes] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()


class FormatAdapter(Protocol):
    """A pluggable exporter for one external format."""

    @property
    def format_id(self) -> str:
        """Stable lowercase identifier, e.g. ``"example_v1"``."""
        ...

    @property
    def display_name(self) -> str: ...

    @property
    def adapter_version(self) -> str: ...

    def capability(self, document: ProjectDocument) -> AdapterCapability:
        """Report whether this document can be exported and what would be lost."""
        ...

    def export(self, document: ProjectDocument) -> AdapterExportResult:
        """Produce the external files. Must not mutate or persist anything."""
        ...


class AdapterRegistryError(Exception):
    pass


class FormatAdapterRegistry:
    """Registered adapters, keyed by ``format_id``. Empty by default."""

    def __init__(self) -> None:
        self._adapters: dict[str, FormatAdapter] = {}

    def register(self, adapter: FormatAdapter) -> None:
        if adapter.format_id in self._adapters:
            raise AdapterRegistryError(
                f"adapter {adapter.format_id!r} is already registered"
            )
        self._adapters[adapter.format_id] = adapter

    def get(self, format_id: str) -> FormatAdapter:
        adapter = self._adapters.get(format_id)
        if adapter is None:
            raise AdapterRegistryError(f"no adapter registered for {format_id!r}")
        return adapter

    def list_adapters(self) -> tuple[FormatAdapter, ...]:
        return tuple(self._adapters[key] for key in sorted(self._adapters))


# Process-wide registry. Intentionally empty in the first release: the native
# archive (project_archive.py) is the supported interchange format.
format_adapters = FormatAdapterRegistry()
