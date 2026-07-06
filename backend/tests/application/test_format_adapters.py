from __future__ import annotations

import pytest

from app.application.exports.adapters import (
    AdapterCapability,
    AdapterExportResult,
    AdapterRegistryError,
    FormatAdapterRegistry,
    format_adapters,
)
from app.domain.project import ProjectDocument, parse_project_document
from tests.sample_paths import load_sample


class _ExampleAdapter:
    """Minimal conforming adapter used only by tests."""

    format_id = "example_lines_v1"
    display_name = "Example line format"
    adapter_version = "0.0.1"

    def capability(self, document: ProjectDocument) -> AdapterCapability:
        unsupported = tuple(f"motion plan {plan.id}" for plan in document.motion_plans)
        return AdapterCapability(
            supported=True,
            detail="exports character names only",
            unsupported_features=unsupported,
        )

    def export(self, document: ProjectDocument) -> AdapterExportResult:
        lines = "\n".join(character.name for character in document.characters)
        return AdapterExportResult(
            files={"characters.txt": lines.encode("utf-8")},
            warnings=("no visual data is exported",),
        )


def test_default_registry_ships_empty() -> None:
    assert format_adapters.list_adapters() == ()


def test_registry_registers_lists_and_rejects_duplicates() -> None:
    registry = FormatAdapterRegistry()
    adapter = _ExampleAdapter()
    registry.register(adapter)
    assert registry.get("example_lines_v1") is adapter
    assert [entry.format_id for entry in registry.list_adapters()] == ["example_lines_v1"]

    with pytest.raises(AdapterRegistryError, match="already registered"):
        registry.register(_ExampleAdapter())
    with pytest.raises(AdapterRegistryError, match="no adapter"):
        registry.get("missing_format")


def test_adapter_receives_document_and_reports_losses() -> None:
    document = parse_project_document(load_sample("projects/biped-demo.rigstory.json"))
    adapter = _ExampleAdapter()

    capability = adapter.capability(document)
    assert capability.supported is True

    result = adapter.export(document)
    assert "characters.txt" in result.files
    assert result.warnings
