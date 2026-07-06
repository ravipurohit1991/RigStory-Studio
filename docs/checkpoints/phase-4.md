# Phase 4 checkpoint

## Delivered

- Deterministic procedural character request schema, normalization ranges, clamping diagnostics, and ten preset fixtures:
  - `backend/app/domain/character_builder.py`
  - `frontend/src/engine/characterBuilder.ts`
  - `samples/fixtures/character-builder-requests.json`
- Canonical biped rig generation from proportions with stable semantic bone IDs, joint limits, controlled asymmetry, and generated arm/leg/look-at constraint metadata.
- Rigid vector part generation for body, limbs, hair, face, clothing, shoes, z-order, pivots, per-part SVG helpers, and combined SVG preview helper.
- Builder diagnostics for invalid dimensions, pivot bounds, visual bone ownership, bilateral mismatch, overlap risk, and clamped request values.
- Character Builder UI with Fluent controls, live Pixi preview, preset/reset controls, deterministic region regeneration, and save-to-project flow:
  - `frontend/src/pages/CharacterBuilderPage.tsx`
  - `frontend/src/components/AppShell.tsx`
  - `frontend/src/styles.css`
- Non-mutating backend preview endpoints:
  - `GET /api/v1/characters/builder-presets`
  - `POST /api/v1/characters/build`

## Acceptance Criteria Evidence

- Ten diverse request fixtures generate valid rigs and visuals: `backend/tests/domain/test_character_builder.py` and `frontend/src/engine/characterBuilder.test.ts`.
- Every generated character uses the existing editable `CharacterDefinition` shape consumed by the rig editor and renderer.
- Left/right semantic IDs and generated constraint descriptors are asserted in backend and frontend tests.
- Fixture output repeatability is asserted by canonical JSON equality and deterministic ID checks.
- Ollama is not required; API and UI tests use only deterministic builders.
- Character Builder workflow is covered in `frontend/tests/e2e/smoke.spec.ts`.

## Commands Run

- `backend`: `python -m ruff check app tests`
- `backend`: `python -m mypy app`
- `backend`: `python -m pytest`
- `frontend`: `npm run generate:client`
- `frontend`: `npm run typecheck`
- `frontend`: `npm run lint`
- `frontend`: `npm test`
- `frontend`: `npm run build`
- `frontend`: `npm run e2e`

## Test Results

- Backend: 100 pytest tests passed.
- Backend: Ruff passed.
- Backend: mypy passed with strict settings.
- Frontend: 81 Vitest tests passed.
- Frontend: ESLint passed.
- Frontend: production build passed.
- E2E: 4 Playwright smoke tests passed, including the generated character save flow and the existing manual wave visual golden.

## Demo Steps

1. Start the backend and frontend with the documented local commands.
2. Open the app and choose **Characters**.
3. Select a preset, adjust proportions and palette controls, and observe the live preview.
4. Regenerate a hair, face, or clothing region.
5. Save the generated character; it is stored as a normal project document.
6. Open **Rig Editor** to inspect and animate editable generated rigs.

## Architecture Changes

- Added a deterministic builder domain module behind normal domain contracts.
- Added generated builder metadata for IK/look-at constraints without changing persisted `RigDefinition`.
- Kept PixiJS behind the renderer adapter; Character Builder imports the adapter dynamically.
- Regenerated OpenAPI artifacts after adding preview endpoints.

## Schema Changes and Migrations

- No persisted project schema migration.
- Added typed API schemas for `CharacterBuilderRequest`, `CharacterBuilderResult`, diagnostics, and generated constraint metadata.
- Generated constraints are preview/build metadata for Phase 4 and are not persisted into project files until a future runtime constraint schema is introduced.

## Known Limitations

- Visuals are rigid primitive vector parts; mesh skinning and richer garment deformation remain future work.
- Region regeneration is deterministic parameter replacement, not AI-assisted semantic editing.
- Build still reports the existing large main chunk warning after production bundling.

## Deferred Work

- Persisted runtime constraint schema and solver integration belong to Phase 7.
- Ollama blueprint generation and generation records belong to Phase 5.
- Scene placement and character library drag-in belong to Phase 6.

## Risks Discovered

- Constraint metadata needs a careful migration path before becoming persisted rig state.
- Frontend and backend deterministic builders intentionally mirror logic; future changes should keep fixture parity tests strong.

## Recommended Next Issue

Begin Phase 5.1: implement `LLMProvider` and `OllamaProvider` so structured character blueprints can feed the deterministic Phase 4 builder.
