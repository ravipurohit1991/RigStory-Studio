# ADR 0008 — Third-party format adapters stay outside the core

**Status:** accepted (Phase 11)

## Context

Users ask whether RigStory projects can be exported to existing skeletal
animation runtimes (Spine, DragonBones, and similar). Those formats are
attractive interchange targets, but their specifications are owned by
commercial products, several reference implementations carry restrictive or
noncommercial licenses, and their feature sets do not map one-to-one onto the
native model (constraint-weight tracks, motion-plan provenance, and mesh
secondary-motion metadata have no direct equivalent).

## Decision

1. The native, versioned `rigstory-project` document and the checksummed
   `rigstory-archive` zip remain the only source-of-truth interchange formats.
2. External formats are supported only through the `FormatAdapter` protocol in
   `backend/app/application/exports/adapters.py`. Adapters:
   - live outside `app/domain` and never appear in domain imports;
   - receive a validated `ProjectDocument` and return files plus warnings;
   - never mutate or persist project state;
   - must report unsupported features explicitly through `AdapterCapability`.
3. No adapter ships in the first release. The registry is empty by default.
4. Before an adapter for a specific format is implemented, its licensing must
   be researched and recorded here (or in a follow-up ADR): specification
   license, reference-runtime license, and whether a clean-room implementation
   is required.
5. RigStory does not promise exact Spine (or any third-party) parity. An
   adapter that cannot represent a feature must degrade with a warning, not
   silently change data.

## Consequences

- The native schema can evolve without being constrained by external formats.
- Format work is isolated, reviewable, and removable.
- Users who need a third-party runtime can see exactly what an adapter loses
  before exporting.
