# Phase 10 checkpoint

## Delivered

- Added project schema `0.6.0` for weighted mesh attachments, including bind
  pose matrices, inverse bind matrices, triangles, normalized vertex weights,
  mesh fill/opacity, smoothing, and secondary-motion metadata.
- Added deterministic CPU skinning in backend and frontend, plus PixiJS adapter
  rendering for mesh triangles.
- Added generated weighted sleeve, trouser, skirt-panel, and outerwear overlay
  meshes while keeping existing rigid attachments in place.
- Added frontend weight-editing helpers for numeric edits, normalization,
  mirroring, and heatmap colors.
- Added regional blueprint merge behavior that locks unrelated fields for
  hair, face, and clothing regeneration.
- Added a provider-neutral optional image-generation contract with provenance
  and segmentation-mask requirements; no image provider is required.

## Acceptance criteria evidence

- Weighted sleeve benchmark character bends through CPU skinning without the
  rigid elbow gap covered by `backend/tests/domain/test_mesh_phase10.py`.
- Weight sums and bone references validate in backend and frontend import
  invariants.
- Rigid-only project samples migrate and validate unchanged through
  `0.5.0 -> 0.6.0`.
- Regional blueprint updates preserve rig/proportions/identity outside the
  requested region.
- Optional image provider absence is represented by a contract only; procedural
  character generation still has no image-provider dependency.

## Commands run

- `python -m pytest`
- `python -m ruff check .`
- `python -m mypy app`
- `python -m mypy app tests` (fails on pre-existing untyped Phase 7-9 tests)
- `python scripts\benchmark_mesh_skinning.py`
- `npm run generate:client`
- `npm run test`
- `npm run lint`
- `npm run typecheck`
- `npm run build`
- `npm run e2e`
- `python scripts\validate_project_samples.py`

## Test results

- Backend: 193 passed.
- Frontend unit: 86 passed.
- Playwright: 6 passed.
- Sample validation: all valid samples accepted; invalid samples rejected as
  expected; legacy migration applies through `0.6.0`.
- Mesh benchmark: 4 meshes, 2,000 iterations, 48,000 vertices, 6,920.564 ms
  total, 865.071 us per mesh on this machine.

## Demo steps

1. Open Character Builder.
2. Choose a preset with `jacket`, `sweater`, `trousers`, `skirt`, or `coat`.
3. Confirm rigid parts still render and mesh clothing overlays follow the rig.
4. Regenerate only hair, face, or clothing and confirm the rig remains
   unchanged.
5. Open the manual rig editor and verify the existing rigid workflows still
   load and render.

## Architecture changes

- Mesh skinning is deterministic domain/engine code.
- PixiJS only renders the evaluated mesh triangles in the renderer adapter.
- Optional image generation is isolated behind
  `ImageGenerationProvider`; it is not part of core character generation.

## Schema changes and migrations

- Project schema changed from `0.5.0` to `0.6.0`.
- Migration `0.5.0 -> 0.6.0` is a compatibility version bump because existing
  attachments remain valid and mesh payloads are optional.
- OpenAPI and generated TypeScript API types were regenerated.

## Known limitations

- Weight editing is currently exposed as deterministic editor helpers and
  renderer support, not a polished paint-brush canvas UI.
- GPU mesh skinning is documented as optional and not required; the shipped path
  is CPU reference skinning.
- Mesh clothing is procedural and simple; it does not simulate cloth.

## Deferred work

- Full brush-based weight painting UI.
- Visual golden specifically comparing rigid and weighted sleeves.
- Optional ComfyUI/local diffusion implementation behind the provider contract.

## Risks discovered

- Full strict mypy over `app tests` still reports older untyped tests in Phase
  7-9 files; application code passes strict mypy.
- The production frontend build still emits the existing large chunk warning.

## Recommended next issue

Begin Phase 11 with native project archive export/import, starting with the
manifest, canonical JSON documents, checksums, and safe extraction tests.
