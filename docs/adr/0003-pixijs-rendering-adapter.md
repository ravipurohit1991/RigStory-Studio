# ADR 0003: PixiJS Rendering Adapter

Status: Accepted

## Context

The frontend needs a high-performance 2D renderer while keeping canonical project state renderer-independent.

## Decision

PixiJS will be used behind renderer adapters. Serialized coordinates remain Y-up and renderer-specific conversion stays in the adapter.

## Consequences

Domain math and project schemas cannot import PixiJS. Renderer changes require adapter tests and visual evidence in later phases.
